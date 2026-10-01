"""Проверяет FeedRows: строки ленты и счёт недосчитанных индексеров рядом с ними."""

from __future__ import annotations

from datetime import UTC, datetime

from torrcast.domain.feed_row import FeedRow
from torrcast.domain.feed_rows import FeedRows
from torrcast.domain.raw_result import RawResult


def _row(name: str) -> FeedRow:
    return FeedRow(RawResult(name, "a" * 40, 1000, 5, "rutor"), datetime(2026, 9, 1, tzinfo=UTC))


def test_an_empty_feed_misses_nobody() -> None:
    """Пустая лента без счёта - не обещание добора: недосчитанных ноль."""
    rows = FeedRows()

    assert rows == []
    assert rows.missed == 0


def test_feed_rows_keep_the_rows_in_order_and_the_missed_count() -> None:
    """Строки идут как пришли, счёт недосчитанных едет рядом и не теряется."""
    first, second = _row("Матрица 1999"), _row("Дюна 2021")

    rows = FeedRows(iter([first, second]), missed=2)

    assert list(rows) == [first, second]
    assert rows.missed == 2
