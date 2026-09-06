"""Проверяет разбор ответа ленты: дата обязательна, битые строки не сдвигают список."""

from __future__ import annotations

import pytest

from torrcast.adapters.prowlarr.from_feed_json import from_feed_json
from torrcast.domain.infra_error import InfraError

_HASH_A = "a" * 40
_HASH_B = "b" * 40


def test_a_row_without_a_publish_date_is_dropped() -> None:
    """Без даты раздачу нечем поместить в окно ленты - строка молча отсеивается."""
    payload = [
        {"title": "Без даты", "infoHash": _HASH_A, "size": 1, "seeders": 1, "indexer": "x"},
        {
            "title": "С датой",
            "infoHash": _HASH_B,
            "size": 1,
            "seeders": 1,
            "indexer": "x",
            "publishDate": "2026-09-01T00:00:00Z",
        },
    ]

    rows = from_feed_json(payload)

    assert [row.raw.info_hash for row in rows] == [_HASH_B]


def test_a_broken_row_does_not_shift_the_dates_of_the_rest() -> None:
    """Битая строка (без hash) выпадает по одной, а не пачкой - соседняя дата на месте."""
    payload = [
        {
            "title": "Без хэша",
            "infoHash": "",
            "size": 1,
            "seeders": 1,
            "indexer": "x",
            "publishDate": "2026-09-01T00:00:00Z",
        },
        {
            "title": "Годная",
            "infoHash": _HASH_A,
            "size": 1,
            "seeders": 1,
            "indexer": "x",
            "publishDate": "2026-09-02T00:00:00Z",
        },
    ]

    rows = from_feed_json(payload)

    assert len(rows) == 1
    assert rows[0].raw.info_hash == _HASH_A
    assert rows[0].published.isoformat() == "2026-09-02T00:00:00+00:00"


def test_a_non_list_payload_is_an_infra_error() -> None:
    with pytest.raises(InfraError, match="unexpected answer"):
        from_feed_json({"error": "нет"})


def test_an_empty_feed_is_an_empty_list() -> None:
    assert from_feed_json([]) == []
