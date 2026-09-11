"""Сезоны и серии карточки (:mod:`web.card`): из закладки или из разбора раздачи."""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.domain.json_value import JsonValue
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan
from web.episode_lookup import EpisodeLookup


def card_seasons(
    plan: Plan, entry: Entry | None, base_url: str, episodes: EpisodeLookup
) -> tuple[list[JsonValue], bool]:
    """Сезоны и серии: из закладки, если она есть; иначе разбор выбранной раздачи.

    Разбор фоновый (:class:`web.episode_lookup.EpisodeLookup`): не готов - вернулась
    ``None``, и карточка честно показывает только счётчик сезонов из имён раздач, помечая
    тело недоехавшим (второй элемент пары), совсем как справку.
    """
    picture = plan.picture
    if picture.kind != "tv":
        return [], False
    if entry is not None and entry.episodes:
        return _seasons_from_entry(entry), False
    numbers = sorted({season for release in picture.releases for season in _named_seasons(release)})
    fallback: list[JsonValue] = [{"n": n, "episodes": []} for n in numbers]
    if not plan.ranked:
        return fallback, False
    table = episodes.table(plan.ranked[0], base_url)
    if table is None:
        return fallback, True
    return (_seasons_from_table(table), False) if table else (fallback, False)


def _named_seasons(release: Release) -> tuple[int, ...]:
    if release.seasons:
        return release.seasons
    return (release.season,) if release.season else ()


def _seasons_from_entry(entry: Entry) -> list[JsonValue]:
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
    return [{"n": n, "episodes": eps} for n, eps in sorted(seasons.items())]


def _seasons_from_table(table: list[list[int]]) -> list[JsonValue]:
    """Серии из разбора раздачи: картину никто не смотрел, отмечать нечего."""
    seasons: dict[int, list[JsonValue]] = {}
    for row in table:
        season, episode = row[0], row[1]
        blank: dict[str, JsonValue] = {"n": episode, "dur": 0.0, "watched": False, "pos": 0.0}
        seasons.setdefault(season, []).append(blank)
    return [{"n": n, "episodes": eps} for n, eps in sorted(seasons.items())]


__all__ = ["card_seasons"]
