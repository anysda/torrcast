"""Карточка сериала собирает вкладки и серии из разных раздач."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, cast

from torrcast.domain.entry import Entry
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan
from web.card_seasons import card_seasons


@dataclass
class _Episodes:
    tables: dict[str, list[list[int]] | None]
    asked: list[str]

    def table(self, release: Release, _base_url: str) -> list[list[int]] | None:
        self.asked.append(release.magnet)
        return self.tables[release.magnet]


def _release(number: int, magnet: str) -> Release:
    return Release(
        raw_name=f"Show / Сезон: {number} WEB-DL 1080p",
        title="Show",
        kind="tv",
        season=number,
        magnet=magnet,
    )


def _plan() -> tuple[Plan, Release, Release]:
    first, second = _release(1, "magnet:first"), _release(2, "magnet:second")
    picture = Picture(title="Show", year=2022, kind="tv", releases=[first, second])
    return Plan(picture=picture, ranked=[first], runtime=1500.0, warn_mbit=12.0), first, second


def _rows(seasons: list[Any]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], seasons)


def test_tabs_are_the_union_and_the_selected_season_uses_its_own_release() -> None:
    plan, first, second = _plan()
    episodes = _Episodes({first.magnet: [[1, 1]], second.magnet: [[2, 1], [2, 2]]}, [])

    seasons, partial = card_seasons(plan, None, "http://torrserver", episodes, season=2)

    assert partial is False
    rows = _rows(seasons)
    assert [row["n"] for row in rows] == [1, 2]
    assert rows[0]["episodes"] == []
    assert [row["n"] for row in rows[1]["episodes"]] == [1, 2]
    assert episodes.asked == [second.magnet]


def test_bookmark_keeps_every_pool_season_and_does_not_choose_its_release_for_another_one() -> None:
    plan, first, second = _plan()
    entry = Entry(
        "Show",
        second.magnet,
        kind="tv",
        season=2,
        episode=2,
        episodes=[[2, 1, 0, 0], [2, 2, 1, 0]],
    )
    episodes = _Episodes({first.magnet: [[1, 1]], second.magnet: [[2, 1], [2, 2]]}, [])

    seasons, partial = card_seasons(plan, entry, "http://torrserver", episodes, season=1)

    assert partial is False
    rows = _rows(seasons)
    assert [row["n"] for row in rows] == [1, 2]
    assert [row["n"] for row in rows[0]["episodes"]] == [1]
    assert [row["n"] for row in rows[1]["episodes"]] == [1, 2]
    assert episodes.asked == [first.magnet]


def test_a_merged_spinoff_does_not_become_a_tab_of_the_opened_show() -> None:
    plan, first, second = _plan()
    short = replace(_release(5, "magnet:short"), title="Show Shorts")
    plan.picture.releases.append(short)
    episodes = _Episodes({first.magnet: [[1, 1]], second.magnet: [[2, 1]]}, [])

    seasons, partial = card_seasons(plan, None, "http://torrserver", episodes)

    assert partial is False
    assert [row["n"] for row in _rows(seasons)] == [1, 2]
