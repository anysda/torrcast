"""Зеркало слова о показе: пауза видна только стоящей закладкой, темнота - не «играю»."""

from __future__ import annotations

from hass.motion import IDLE, PAUSED, PLAYING, STARTING, TORN, Motion
from torrcast.domain.playback_snapshot import PlaybackSnapshot


class _Clock:
    """Часы теста: время идёт ровно туда, куда его двигают."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _shown(position: float, dark: float = 0.0) -> PlaybackSnapshot:
    return PlaybackSnapshot(
        key="movie:муха", title="Муха", position=position, duration=3600.0, dark_since=dark
    )


def test_a_bookmark_that_keeps_moving_is_never_called_a_pause() -> None:
    clock = _Clock()
    motion = Motion(still=25.0, clock=clock)

    assert motion.phase(_shown(60.0), active=True, starting=False) == PLAYING
    clock.now = 30.0
    assert motion.phase(_shown(90.0), active=True, starting=False) == PLAYING


def test_a_bookmark_standing_longer_than_the_threshold_is_a_pause() -> None:
    clock = _Clock()
    motion = Motion(still=25.0, clock=clock)

    motion.phase(_shown(60.0), active=True, starting=False)
    clock.now = 20.0  # сторож показа пишет закладку раз в 10 с: тут ещё не пауза
    assert motion.phase(_shown(60.0), active=True, starting=False) == PLAYING
    clock.now = 26.0
    assert motion.phase(_shown(60.0), active=True, starting=False) == PAUSED


def test_a_dark_screen_is_not_called_playing_even_with_a_live_unit() -> None:
    motion = Motion(clock=_Clock())

    assert motion.phase(_shown(60.0, dark=1.0), active=True, starting=False) == TORN


def test_a_show_that_is_being_started_and_a_silent_machine() -> None:
    motion = Motion(clock=_Clock())

    assert motion.phase(None, active=False, starting=True) == STARTING
    assert motion.phase(None, active=False, starting=False) == IDLE
