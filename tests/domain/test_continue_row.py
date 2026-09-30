"""Ряд «Продолжить» службы совпадает с тем, что рисует главная."""

from __future__ import annotations

from torrcast.domain.continue_row import continue_row
from torrcast.domain.entry import Entry


def _entry(updated: str, watched: bool = False) -> Entry:
    return Entry(
        title=updated, magnet="", updated=updated, pos=100.0 if watched else 50.0, dur=100.0
    )


def test_the_row_is_the_unwatched_records_freshest_first() -> None:
    entries = {
        "old": _entry("2026-09-01T00:00:00+00:00"),
        "seen": _entry("2026-09-30T00:00:00+00:00", watched=True),
        "new": _entry("2026-09-29T00:00:00+00:00"),
    }

    assert continue_row(entries) == ["new", "old"]
