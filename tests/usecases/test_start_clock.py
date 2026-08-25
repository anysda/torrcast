"""Зеркально проверяет часы старта показа."""

from torrcast.usecases.start_clock import _Clock


def test_clock_measures_the_whole_start() -> None:
    clock = _Clock()

    assert clock.total >= 0.0
