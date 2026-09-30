"""Проверяет shelf_lane: в очередь приговоров идут только записи с обложкой, по порядку."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue
from web.shelf_lane import shelf_lane


def test_only_covered_records_queue_for_a_verdict_in_shelf_order() -> None:
    records: list[JsonValue] = [
        {"query": "q1", "key": "k1", "poster": "p"},
        {"query": "q2", "key": "k2"},
        "not a record",
        {"query": "q3", "key": "k3", "poster": "p"},
    ]

    assert shelf_lane(records) == [("q1", "k1"), ("q3", "k3")]
