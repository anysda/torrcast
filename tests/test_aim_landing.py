"""Защёлка места моста держится, пока запись показа не назовёт именно её место.

Числа - с живого приёмника 06-10-2026 (кнопка карточки, пять нажатий «назад» подряд).
"""

from __future__ import annotations

from hass.aim import Aim
from torrcast.domain.playback_snapshot import PlaybackSnapshot


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _place(aim: Aim, position: float) -> float:
    shown = PlaybackSnapshot(
        key="movie:k", title="K", position=position, duration=9000.0, moved=True, paused=""
    )
    answered = aim.seen(shown)
    assert answered is not None
    return answered.position


def _five_back(aim: Aim, clock: _Clock, truth: float) -> None:
    _place(aim, truth)
    for _ in range(5):
        aim.at(-60.0)
    clock.now = 0.0


def test_the_first_of_two_seeks_in_the_record_is_not_the_landing() -> None:
    """Показ взял нажатия как ``-240`` и ``-60``: запись успела назвать первую."""
    clock = _Clock()
    aim = Aim(clock=clock)
    _five_back(aim, clock, 1460.4)

    clock.now = 4.7
    assert round(_place(aim, 1236.5), 1) == 1165.1
    clock.now = 14.9
    assert _place(aim, 1176.8) == 1176.8


def test_the_latch_waits_out_the_tv_buffering_before_the_record_moves() -> None:
    """Запись назвала новое место через 20.8 с, до того стояла у старого."""
    clock = _Clock()
    aim = Aim(clock=clock)
    _five_back(aim, clock, 1183.1)

    clock.now = 16.0
    assert round(_place(aim, 1183.1), 1) == 899.1
    clock.now = 20.8
    assert _place(aim, 896.7) == 896.7
