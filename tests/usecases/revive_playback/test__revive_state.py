"""Зеркало общего места оживления: слово композиции читают и лестница, и держатель."""

from __future__ import annotations

from pathlib import Path

import torrcast.usecases.revive_playback._revive_state as _state
from tests.fakes.clock import FakeClock
from torrcast.usecases.revive_playback._revival import _Revival
from torrcast.usecases.revive_playback._revive_state import TAIL_LIMIT, _configure_revive_playback


def test_the_configured_clock_becomes_the_default_of_the_ladder() -> None:
    """Часы кладут один раз, а берёт их лестница, которую завели без своих часов."""
    previous_clock = getattr(_state, "_revive_clock", None)
    previous_mark = getattr(_state, "_revive_playing_mark", None)
    marked: list[Path] = []
    given = FakeClock(now=500.0)
    try:
        _configure_revive_playback(given, marked.append)

        assert _Revival().clock is given
        _state._revive_playing_mark(Path("/tmp/hls"))
        assert marked == [Path("/tmp/hls")]
    finally:
        if previous_clock is not None and previous_mark is not None:
            _configure_revive_playback(previous_clock, previous_mark)


def test_a_second_word_replaces_the_first() -> None:
    """Композиция сказала заново - лестница берёт новые часы, а не первые."""
    previous_clock = getattr(_state, "_revive_clock", None)
    previous_mark = getattr(_state, "_revive_playing_mark", None)
    try:
        _configure_revive_playback(FakeClock(now=1.0), lambda _path: None)
        second = FakeClock(now=2.0)
        _configure_revive_playback(second, lambda _path: None)

        assert _Revival().clock is second
    finally:
        if previous_clock is not None and previous_mark is not None:
            _configure_revive_playback(previous_clock, previous_mark)


def test_the_tail_guard_is_a_whole_minute() -> None:
    """Страховка перехода длиной в минуту: короче - и живой хвост считался бы концом."""
    assert TAIL_LIMIT == 60.0
