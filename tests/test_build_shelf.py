"""Проверяет сборку одной полки: запас кандидатов, обложки, приговор, предел видимых."""

from __future__ import annotations

from datetime import UTC, datetime

from torrcast.adapters.prowlarr.torrent_catalogue import torrent_catalogue
from torrcast.domain.facts.origin import Origin
from torrcast.domain.feed_row import FeedRow
from torrcast.domain.json_value import JsonValue
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.shelves.fresh_shelf import LIMIT
from web.build_shelf import build_shelf

_MOMENT = datetime(2026, 9, 6, tzinfo=UTC)


def _rows(count: int) -> list[FeedRow]:
    return [
        FeedRow(
            RawResult(f"Картина {index:02d} 2026 1080p", f"{index:040x}", 1000, 5, "rutor"),
            datetime(2026, 9, 5, tzinfo=UTC),
        )
        for index in range(count)
    ]


def _odd_posters(records: list[JsonValue]) -> list[JsonValue]:
    """Обложка только у каждой второй картины."""
    return [
        {**record, "poster": "abc"} if index % 2 and isinstance(record, dict) else record
        for index, record in enumerate(records)
    ]


def _titles(tiles: list[JsonValue]) -> list[str]:
    return [str(tile["title"]) for tile in tiles if isinstance(tile, dict)]


def _passport(_title: str, _series: bool, _timeout: float) -> Origin:
    return Origin()


def test_pictures_without_a_poster_give_their_place_to_the_next_covered_ones() -> None:
    """Полка добирается из запаса кандидатов до предела, а не усыхает вдвое."""
    tiles = build_shelf(
        "fresh",
        _rows(LIMIT * 3),
        torrent_catalogue,
        _odd_posters,
        _passport,
        lambda query, key: True,
        _MOMENT,
    )

    assert len(tiles) == LIMIT
    assert all(isinstance(tile, dict) and tile["poster"] for tile in tiles)


def test_a_picture_judged_unplayable_does_not_reach_the_shelf() -> None:
    """Честное «не играет» снимает плитку, «не знаем» её оставляет."""
    verdicts = {"Картина 00": False, "Картина 01": None}

    tiles = build_shelf(
        "popular",
        _rows(3),
        torrent_catalogue,
        lambda records: [{**r, "poster": "abc"} for r in records if isinstance(r, dict)],
        _passport,
        lambda query, key: verdicts.get(query, True),
        _MOMENT,
    )

    assert "Картина 00" not in _titles(tiles)
    assert "Картина 01" in _titles(tiles)
    assert len(tiles) == 2
