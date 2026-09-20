"""Сезоны и серии карточки (:mod:`web.card`): из закладки или из разбора раздачи."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from torrcast.domain.entry import Entry
from torrcast.domain.episode import Episode
from torrcast.domain.json_value import JsonValue
from torrcast.domain.magnet_hash import magnet_hash
from torrcast.domain.picture import Picture
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.recodes_whole import recodes_whole
from torrcast.domain.release import Release
from torrcast.domain.slugify import slugify
from torrcast.usecases.rank.gate_open import gate_open
from torrcast.usecases.rank.last_hope import last_hope
from torrcast.usecases.rank.rank_releases import rank_releases
from torrcast.usecases.select.plan import Plan
from web.episode_absent import ABSENT
from web.mark_empty import mark_empty
from web.seasons_from_entry import seasons_from_entry


class _Catalog(Protocol):
    def rows(
        self, picture: Picture, releases: Sequence[Release], saved: dict[int, list[JsonValue]]
    ) -> tuple[dict[int, list[JsonValue]], bool, list[int]]: ...


class _EpisodeTables(Protocol):
    """Кэш таблиц серий, достаточный карточке."""

    def table(self, release: Release, base_url: str) -> list[list[int]] | None: ...


def card_seasons(
    plan: Plan,
    entry: Entry | None,
    base_url: str,
    episodes: _EpisodeTables,
    season: int | None = None,
    profile: Profile = CAUTIOUS,
    catalog: _Catalog | None = None,
) -> tuple[list[JsonValue], bool, Release | None, list[int]]:
    """Все вкладки и серии: из каталога сериала, иначе из покрывающей сезон раздачи.

    Сериал из каталога (:class:`web.series_catalog.SeriesCatalog`) получает все сезоны и
    серии сразу; закладка накладывается на них по номеру серии и главнее каталога.
    Разбор раздачи фоновый (:class:`web.episode_lookup.EpisodeLookup`): не готов - вернулась
    ``None``, и карточка честно показывает только счётчик сезонов из имён раздач, помечая
    тело недоехавшим (второй элемент), совсем как справку. Четвёртый - числа серий сезонов
    списка каталога, который нумерует сериал не как раздачи: вкладки тогда только его.

    Вышедшие серии открытого сезона, которых нет ни в одной раздаче, называет
    :class:`web.episode_absent.EpisodeAbsent` полем ``absent`` сезона. Перебор раздач
    ответ не держит: не договорил - тело помечено недоехавшим, и приговор приезжает
    следующим добором, а до него строка обычная и нажимается. Сезон, за которым не нашлось
    ни одной серии, несёт поле ``empty`` (:mod:`web.mark_empty`).
    """
    picture = plan.picture
    if picture.kind != "tv":
        return [], False, None, []
    releases = _picture_releases(plan)
    numbers = {number for release in releases for number in _named_seasons(release)}
    saved = seasons_from_entry(entry) if entry is not None and entry.episodes else {}
    known, pending, layout = catalog.rows(picture, releases, saved) if catalog else ({}, False, [])
    numbers = set(known) if layout else numbers | set(known) | set(saved)
    # Без выбранной вкладки открыт сезон закладки, как у стримингов: таблица нужна ему.
    bookmark = entry.season if entry is not None else None
    default = bookmark if bookmark in numbers else (1 if 1 in numbers else min(numbers, default=0))
    target = season if season in numbers else default
    fallback, hunting = ABSENT.of(
        _joined_seasons(numbers, known or saved),
        picture.key,
        target,
        releases,
        episodes,
        base_url,
        saved,
        bool(layout),
    )
    release = _release_for(plan, releases, target, entry, profile)
    if release is None or target in known:
        later = pending or hunting
        return mark_empty(fallback, target, not later), later, release, layout
    table = episodes.table(release, base_url)
    if table is None:
        return fallback, True, release, []
    files = _seasons_from_table(table)
    if target not in files and target not in _named_seasons(release):
        # Пак без сезона «покрывает» любой, но файлы «Универа» кончаются на s04: сезон 5 играет
        # раздача, которая его называет, первая тем же порядком отбора.
        naming = [other for other in releases if target in _named_seasons(other)]
        named = _release_for(plan, naming, target, entry, profile) if naming else None
        table = episodes.table(named, base_url) if named is not None else table
        if named is not None and table is None:
            return fallback, True, named, []
        files, release = _seasons_from_table(table or []), named or release
    numbers.update(files)  # Полный пак без сезона в имени называет сезоны своими файлами.
    # Закладка хранит просмотренное состояние и старше безличной таблицы файлов.
    rows = _joined_seasons(numbers, {**files, **(known or saved)})
    return mark_empty(rows, target, True), False, release, []


def _named_seasons(release: Release) -> tuple[int, ...]:
    if release.seasons:
        return release.seasons
    return (release.season,) if release.season else ()


def _picture_releases(plan: Plan) -> list[Release]:
    """Не принять слившийся спин-офф за следующий сезон открытой картины."""
    picture = plan.picture
    names = {slugify(name) for name in (picture.title, picture.original or "") if name}
    same_picture = [
        release
        for release in picture.releases
        if names.intersection(slugify(name) for name in (release.title, release.original or ""))
    ]
    return same_picture or picture.releases


def _release_for(
    plan: Plan, releases: list[Release], season: int, entry: Entry | None, profile: Profile
) -> Release | None:
    """Раздача, с которой показ сыграл бы сезон: первая в отборе, что его покрывает.

    Отбор плана покрывает сезон плана; чужой сезон показ отбирает своим порядком из тех
    же раздач, что его покрывают (:func:`torrcast.usecases.reinforce.plan_for.plan_for`),
    и тем же профилем приёмника. Сезон в строках закладки играет раздача закладки, и её
    нет в пуле - всё равно она (TC-1263: закладка главнее), а не первая по рангу молча.
    """
    if entry is not None and any(row[0] == season for row in entry.episodes):
        saved = magnet_hash(entry.magnet)
        if saved:
            pooled = (release for release in releases if magnet_hash(release.magnet) == saved)
            return next(pooled, None) or _bookmark_release(entry)
    own = plan.series is None or plan.series.want.season == season
    ranked = (release for release in plan.ranked if own and release in releases)
    chosen = next((release for release in ranked if release.covers(season)), None)
    if chosen is not None:
        return chosen
    # Строка серии играет эту раздачу, поэтому чужой сезон ставит порядок отбора ЭТОГО
    # сезона, а не выдачи и не сезона плана: у «Рика и Морти» так вставала 360p для КПК.
    covering = [release for release in releases if release.covers(season)]
    if not covering:
        return None
    want, runtime, ceiling, hard = Episode(season, 1), plan.runtime, plan.warn_mbit, plan.hard_mbit
    loose = gate_open(covering, runtime, ceiling, want, hard, copy_hevc=plan.copy_hevc)
    last = (
        plan.recode_at > 0
        and recodes_whole("hevc", profile.copy_depth, profile)
        and last_hope(covering, runtime, ceiling, want, loose, hard, copy_hevc=plan.copy_hevc)
    )
    return rank_releases(
        covering,
        runtime,
        ceiling,
        want=want,
        loose=loose,
        hard_mbit=hard,
        last=last,
        copy_hevc=plan.copy_hevc,
        studio=plan.studio,
        recode_at=plan.recode_at,
        profile=profile,
    )[0]


def _bookmark_release(entry: Entry) -> Release:
    """Раздача закладки, которой нет в пуле: её файлы разбираются по магниту закладки."""
    seasons = tuple(sorted({row[0] for row in entry.episodes}))
    single = seasons[0] if len(seasons) == 1 else None
    return Release(
        raw_name=entry.title,
        title=entry.title,
        kind="tv",
        season=single,
        seasons=() if single else seasons,
        magnet=entry.magnet,
    )


def _seasons_from_table(table: list[list[int]]) -> dict[int, list[JsonValue]]:
    """Серии из разбора раздачи: картину никто не смотрел, отмечать нечего."""
    seasons: dict[int, list[JsonValue]] = {}
    for row in table:
        season, episode = row[0], row[1]
        blank: dict[str, JsonValue] = {"n": episode, "dur": 0.0, "watched": False, "pos": 0.0}
        seasons.setdefault(season, []).append(blank)
    return seasons


def _joined_seasons(numbers: set[int], known: dict[int, list[JsonValue]]) -> list[JsonValue]:
    return [{"n": number, "episodes": known.get(number, [])} for number in sorted(numbers)]


__all__ = ["card_seasons"]
