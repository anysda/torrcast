"""Часы поверх стандартного времени идут вперёд и умеют ждать."""

from torrcast.adapters.system_clock import SystemClock


def test_the_clock_answers_both_kinds_of_time() -> None:
    clock = SystemClock()

    assert clock.monotonic() > 0.0
    assert clock.wall() > 1_600_000_000.0


def test_sleeping_moves_the_monotonic_reading() -> None:
    clock = SystemClock()
    before = clock.monotonic()

    clock.sleep(0.01)

    assert clock.monotonic() - before >= 0.01
