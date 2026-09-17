"""Прогрев по телу полок: первые видимые плитки сразу, остальное - следом."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue
from web.shelf_warm_targets import VISIBLE, shelf_warm_targets


def _tiles(count: int, *, prefix: str = "fresh") -> list[JsonValue]:
    return [
        {
            "query": f"{prefix}{index}",
            "key": f"movie:{prefix}{index}",
            "title": f"Картина {index}",
            "year": 2026,
            "kind": "movie",
        }
        for index in range(count)
    ]


def test_the_first_visible_tiles_of_both_shelves_come_back() -> None:
    body: dict[str, JsonValue] = {
        "fresh": _tiles(10, prefix="f"),
        "popular": _tiles(10, prefix="p"),
    }

    targets = shelf_warm_targets(body)

    assert len(targets) == VISIBLE * 2
    assert {key for _, key, *_ in targets} == {f"movie:f{i}" for i in range(VISIBLE)} | {
        f"movie:p{i}" for i in range(VISIBLE)
    }


def test_later_targets_skip_the_already_warmed_visible_tiles() -> None:
    body: dict[str, JsonValue] = {
        "fresh": _tiles(12, prefix="f"),
        "popular": _tiles(12, prefix="p"),
    }

    warmed = {key for _, key, *_ in shelf_warm_targets(body)}
    later = {key for _, key, *_ in shelf_warm_targets(body, later=True)}

    assert not warmed & later
    assert len(later) == (12 - VISIBLE) * 2


def test_a_malformed_tile_is_skipped_not_crashed_on() -> None:
    body: dict[str, JsonValue] = {"fresh": [{"title": "без года и рода"}], "popular": []}

    assert shelf_warm_targets(body) == []


def test_a_missing_shelf_reads_as_empty() -> None:
    assert shelf_warm_targets({}) == []
