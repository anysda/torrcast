"""Сезоны и серии карточки (:mod:`web.card`): из закладки или из разбора раздачи."""

from __future__ import annotations

from typing import Protocol

from torrcast.domain.entry import Entry
from torrcast.domain.json_value import JsonValue
from torrcast.domain.release import Release
from torrcast.domain.slugify import slugify
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
) -> tuple[list[JsonValue], bool]:
    """Все вкладки пула и серии выбранного сезона из покрывающей его раздачи.

    Разбор фоновый (:class:`web.episode_lookup.EpisodeLookup`): не готов - вернулась
    ``None``, и карточка честно показывает только счётчик сезонов из имён раздач, помечая
    тело недоехавшим (второй элемент пары), совсем как справку.
    """
    picture = plan.picture
    if picture.kind != "tv":
        return [], False
    releases = _picture_releases(plan)
    numbers = {number for release in releases for number in _named_seasons(release)}
    saved = _seasons_from_entry(entry) if entry is not None and entry.episodes else {}
    numbers.update(saved)
    target = season if season in numbers else (1 if 1 in numbers else min(numbers, default=0))
    fallback = _joined_seasons(numbers, saved)
    release = _release_for(plan, releases, target)
    if release is None:
        return fallback, False
    table = episodes.table(release, base_url)
    if table is None:
        return fallback, True
    return _joined_seasons(numbers, _with_table(saved, _seasons_from_table(table))), False


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


def _release_for(plan: Plan, releases: list[Release], season: int) -> Release | None:
    """Взять раздачу, которая НАЗВАЛА сезон, и лишь затем молчащую о нём."""
    choices = [*(release for release in plan.ranked if release in releases), *releases]
    named = next((release for release in choices if season in _named_seasons(release)), None)
    return named or next((release for release in choices if release.covers(season)), None)


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
