"""Сезоны и серии карточки (:mod:`web.card`): из закладки или из разбора раздачи."""

from __future__ import annotations

from typing import Protocol

from torrcast.domain.entry import Entry
from torrcast.domain.episode import Episode
from torrcast.domain.json_value import JsonValue
from torrcast.domain.magnet_hash import magnet_hash
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.recodes_whole import recodes_whole
from torrcast.domain.release import Release
from torrcast.domain.slugify import slugify
from torrcast.usecases.rank.gate_open import gate_open
from torrcast.usecases.rank.last_hope import last_hope
from torrcast.usecases.rank.rank_releases import rank_releases
from torrcast.usecases.select.plan import Plan


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
) -> tuple[list[JsonValue], bool, Release | None]:
    """Все вкладки пула и серии выбранного сезона из покрывающей его раздачи.

    Разбор фоновый (:class:`web.episode_lookup.EpisodeLookup`): не готов - вернулась
    ``None``, и карточка честно показывает только счётчик сезонов из имён раздач, помечая
    тело недоехавшим (второй элемент пары), совсем как справку.
    """
    picture = plan.picture
    if picture.kind != "tv":
        return [], False, None
    releases = _picture_releases(plan)
    numbers = {number for release in releases for number in _named_seasons(release)}
    saved = _seasons_from_entry(entry) if entry is not None and entry.episodes else {}
    numbers.update(saved)
    # Без выбранной вкладки открыт сезон закладки, как у стримингов: таблица нужна ему.
    bookmark = entry.season if entry is not None else None
    default = bookmark if bookmark in numbers else (1 if 1 in numbers else min(numbers, default=0))
    target = season if season in numbers else default
    fallback = _joined_seasons(numbers, saved)
    release = _release_for(plan, releases, target, entry, profile)
    if release is None:
        return fallback, False, None
    table = episodes.table(release, base_url)
    if table is None:
        return fallback, True, release
    files = _seasons_from_table(table)
    # Полный пак без сезона в имени называет сезоны только своими файлами.
    numbers.update(files)
    return _joined_seasons(numbers, _with_table(saved, files)), False, release


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
    и тем же профилем приёмника. Сезон в строках закладки играет раздача закладки.
    """
    if entry is not None and any(row[0] == season for row in entry.episodes):
        saved = magnet_hash(entry.magnet)
        bookmark = (
            next((release for release in releases if magnet_hash(release.magnet) == saved), None)
            if saved
            else None
        )
        if bookmark is not None:
            return bookmark
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


def _seasons_from_entry(entry: Entry) -> dict[int, list[JsonValue]]:
    at = entry.where(entry.season or 0, entry.episode or 0)
    seasons: dict[int, list[JsonValue]] = {}
    for index, row in enumerate(entry.episodes):
        season, episode = row[0], row[1]
        current = index == at
        seasons.setdefault(season, []).append(
            {
                "n": episode,
                "dur": entry.dur if current else 0.0,
                "watched": entry.watched if current else index < at,
                "pos": entry.pos if current else 0.0,
            }
        )
    return seasons


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


def _with_table(
    saved: dict[int, list[JsonValue]], table: dict[int, list[JsonValue]]
) -> dict[int, list[JsonValue]]:
    """Закладка хранит просмотренное состояние и старше безличной таблицы файлов."""
    return {**table, **saved}


__all__ = ["card_seasons"]
