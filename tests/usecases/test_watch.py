"""Зеркально проверяет сторожа позиции показа."""

from torrcast.usecases.watch import WATCH_SECONDS, Watch


def test_watch_keeps_its_tick_and_its_api() -> None:
    assert WATCH_SECONDS == 10.0
    assert {"see", "close", "flush"} <= set(vars(Watch))
