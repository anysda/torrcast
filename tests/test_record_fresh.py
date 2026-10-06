"""Место записи юнита на сейчас: счёт идущего показа и где он стоит (:mod:`hass.record_fresh`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hass.record_fresh import FRESH_SECONDS, record_fresh
from torrcast.domain.playback_snapshot import PlaybackSnapshot

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def _shown(word: str = "PLAYING", age: float = 4.0, **kwargs: object) -> PlaybackSnapshot:
    fields: dict[str, object] = {
        "key": "movie:муха",
        "title": "Муха",
        "position": 737.9,
        "duration": 7200.0,
        "moved": True,
        "paused": word,
        "updated": (NOW - timedelta(seconds=age)).isoformat(),
    }
    fields.update(kwargs)
    return PlaybackSnapshot(**fields)  # type: ignore[arg-type]


def _at_now(shown: PlaybackSnapshot) -> float:
    return record_fresh(shown, now=lambda: NOW).position


def test_a_playing_record_is_counted_on_by_its_age() -> None:
    assert _at_now(_shown(age=4.0)) == pytest.approx(741.9)


def test_the_count_stops_at_the_tick_with_a_margin_and_at_the_end() -> None:
    """Запись старше тика сторожа - юнит не пишет; и дальше конца фильма места нет."""
    assert _at_now(_shown(age=300.0)) == pytest.approx(737.9 + FRESH_SECONDS)
    assert _at_now(_shown(age=8.0, duration=740.0)) == pytest.approx(740.0)


@pytest.mark.parametrize(
    "shown",
    [
        _shown("PAUSED"),
        _shown("BUFFERING"),
        _shown(moved=False),
        _shown(updated=""),
        _shown(updated="не время"),
        _shown(age=-30.0),
    ],
    ids=["pause", "buffer", "not-moved", "no-stamp", "bad-stamp", "stamp-ahead"],
)
def test_a_record_that_is_not_running_keeps_its_place(shown: PlaybackSnapshot) -> None:
    assert _at_now(shown) == pytest.approx(737.9)
