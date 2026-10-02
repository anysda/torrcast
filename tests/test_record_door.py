"""Дверь держателя записей: вызовы к службе по одному и после подъёма показа."""

from __future__ import annotations

import threading

import pytest

from web.record_door import STEP, YIELD, RecordDoor


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def wait(self, seconds: float) -> None:
        self.now += seconds


def test_a_call_waits_for_the_show_to_start() -> None:
    """🔴 Клик раньше фоновой работы записей: пока показ поднимается, вызова нет."""
    clock = _Clock()
    door = RecordDoor(starting=lambda: clock.now < 7.0, clock=lambda: clock.now, wait=clock.wait)

    with door.call():
        entered = clock.now

    assert 7.0 <= entered < 7.0 + STEP


def test_a_stuck_show_start_holds_a_call_no_longer_than_yield() -> None:
    """Подъём, который не кончается, держит фоновый вызов не дольше :data:`YIELD`."""
    clock = _Clock()
    door = RecordDoor(starting=lambda: True, clock=lambda: clock.now, wait=clock.wait)

    with door.call():
        entered = clock.now

    assert YIELD <= entered < YIELD + STEP


@pytest.mark.machine
def test_calls_go_one_at_a_time() -> None:
    """Аренды разных записей не кладут вызовы в службу пачкой: следующий ждёт прошлый."""
    door = RecordDoor(starting=lambda: False)
    inside, leave, second = threading.Event(), threading.Event(), threading.Event()

    def first() -> None:
        with door.call():
            inside.set()
            leave.wait(5)

    def other() -> None:
        with door.call():
            second.set()

    threading.Thread(target=first, daemon=True).start()
    assert inside.wait(5)
    threading.Thread(target=other, daemon=True).start()
    assert not second.wait(0.3), "второй вызов вошёл, пока первый ещё в службе"
    leave.set()
    assert second.wait(5)
