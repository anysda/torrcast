"""Зеркально проверяет часы фаз старта показа."""

from torrcast.usecases.start_clock import _Clock


def test_clock_measures_laps_and_the_whole_start() -> None:
    clock = _Clock()

    assert clock.lap().endswith(" с")
    assert clock.total >= 0.0
