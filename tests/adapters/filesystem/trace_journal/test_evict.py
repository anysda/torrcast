"""Схема ``warm/evict``: бюджет прогрева вытеснил чужой каталог."""

from __future__ import annotations

import pytest

from tests.adapters.filesystem.trace_journal.tape import caught
from torrcast.adapters.filesystem.trace_journal.evict import evict


def test_the_record_says_who_was_evicted_how_much_it_freed_and_what_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Освобождённое и потребное стоят рядом: иначе не видно, хватило ли вытеснения.

    Название картины - украшение для человека, а решает разбор по ключу: он один и тот же
    у прогрева, у бюджета и у каталога на диске.
    """
    seen = caught(monkeypatch)

    evict(key="tt1234567", freed=8_000_000_000, need=13_300_000_000, title="Моана 2")

    assert seen == [
        (
            "warm",
            "evict",
            {
                "key": "tt1234567",
                "title": "Моана 2",
                "freed": 8_000_000_000,
                "need": 13_300_000_000,
            },
        )
    ]
