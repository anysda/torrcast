"""Строки серий закладки: просмотренное до места, ход и длительность - только у текущей."""

from __future__ import annotations

from typing import Any, cast

from torrcast.domain.entry import Entry
from web.seasons_from_entry import seasons_from_entry


def _entry() -> Entry:
    return Entry(
        "Show",
        "magnet:show",
        kind="tv",
        season=2,
        episode=2,
        episodes=[[1, 1, 0, 0], [2, 1, 1, 0], [2, 2, 2, 0], [2, 3, 3, 0]],
        pos=300.0,
        dur=1500.0,
    )


def test_every_episode_before_the_place_is_watched_and_only_it_carries_the_position() -> None:
    rows = seasons_from_entry(_entry())
    seasons = {season: cast(list[Any], cells) for season, cells in rows.items()}

    assert sorted(seasons) == [1, 2]
    assert [(row["n"], row["watched"]) for row in seasons[2]] == [(1, True), (2, False), (3, False)]
    places = [(row["pos"], row["dur"]) for row in seasons[2]]
    assert places == [(0.0, 0.0), (300.0, 1500.0), (0.0, 0.0)]
    assert [row["watched"] for row in seasons[1]] == [True]


def test_an_entry_without_episodes_has_no_rows() -> None:
    assert seasons_from_entry(Entry("Show", "magnet:show", kind="tv")) == {}
