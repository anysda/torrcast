"""Проверяет добор ленты к сроку: переспрос только недосчитанных и только до срока."""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest

from torrcast.domain.feed_row import FeedRow
from torrcast.domain.feed_rows import FeedRows
from torrcast.domain.raw_result import RawResult
from web.feed_refill import FeedRefill


def _row(name: str) -> FeedRow:
    return FeedRow(RawResult(name, "b" * 40, 1000, 5, "rutor"), datetime(2026, 9, 1, tzinfo=UTC))


def _finish(refill: FeedRefill) -> None:
    if refill._thread is not None:
        refill._thread.join(5)


def test_a_whole_feed_starts_nothing() -> None:
    refill = FeedRefill(None, time.monotonic() + 5).start()

    assert refill._thread is None
    assert not refill.short and not refill.pending() and refill.take() == []


def test_an_indexer_that_answers_in_time_brings_its_rows(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Недосчитанный ответил к сроку: строки забираются, недосчёта больше нет, журнал - когда."""
    refill = FeedRefill(lambda _within: FeedRows([_row("Дюна 2021")]), time.monotonic() + 5)

    _finish(refill.start())

    assert refill.pending()  # rows not yet taken hold the shelf open past the thread
    assert [row.raw.title for row in refill.take()] == ["Дюна 2021"]
    assert refill.take() == []
    assert not refill.short
    journal = capsys.readouterr().out
    assert "re-asking for" in journal or "переспрос ещё" in journal
    assert "1 rows, missed 0" in journal or "дал 1 строк, недосчитано 0" in journal


def test_a_refusing_indexer_is_re_asked_with_a_pause_until_the_deadline() -> None:
    """Отказ за отказом: переспрос не долбит Prowlarr и встаёт на сроке, недосчёт остаётся."""
    calls: list[float] = []

    def again(_within: float) -> FeedRows:
        calls.append(time.monotonic())
        return FeedRows([], missed=1, again=again)

    began = time.monotonic()
    refill = FeedRefill(again, began + 0.3).start()
    assert refill.pending()
    _finish(refill)

    assert len(calls) == 1  # the pause outlasts the deadline
    assert time.monotonic() - began < 1.0
    assert refill.short and not refill.pending()
