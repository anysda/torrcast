"""Часы ленты показа: договор узок ровно настолько, чтобы им был сам ``time``."""

from __future__ import annotations

import time

from torrcast.ports.feed_clock import FeedClock


def test_the_standard_time_module_is_a_clock_of_the_feed() -> None:
    """Слот заполняет композиция самим :mod:`time`: договор обязан им приниматься."""
    clock: FeedClock = time
    assert clock.monotonic() > 0.0


def test_a_hand_moved_clock_is_a_clock_too() -> None:
    """Стенду нужна ручная стрелка, и договор не требует от неё ничего лишнего."""

    class Hand:
        def __init__(self) -> None:
            self.now = 1000.0

        def monotonic(self) -> float:
            return self.now

        def sleep(self, seconds: float) -> None:
            self.now += seconds

    clock: FeedClock = Hand()
    clock.sleep(2.5)
    assert clock.monotonic() == 1002.5
