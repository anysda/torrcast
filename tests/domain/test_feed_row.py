"""Проверяет FeedRow: неизменяемая пара сырой строки и времени её первой раздачи."""

from __future__ import annotations

from datetime import UTC, datetime

from torrcast.domain.feed_row import FeedRow
from torrcast.domain.raw_result import RawResult


def test_a_feed_row_carries_the_raw_result_and_its_publish_time() -> None:
    """Строка ленты не меняет сырую находку, а лишь несёт рядом с ней дату."""
    raw = RawResult("Матрица 1999", "a" * 40, 1000, 5, "rutor")
    published = datetime(2026, 9, 1, tzinfo=UTC)

    row = FeedRow(raw, published)

    assert row.raw is raw
    assert row.published == published
