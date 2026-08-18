"""Часы ленты показа: монотонная стрелка и сон, и ничего сверх них."""

from typing import Protocol


class FeedClock(Protocol):
    """Часы в том объёме, в каком их знает лента показа.

    Уже общего порта часов (:class:`torrcast.ports.clock.Clock`) намеренно: лента не
    спрашивает стенных секунд вовсе, а слот обязан принимать сам :mod:`time` - им его и
    заполняет композиция (:func:`torrcast.runtime.wire_feed.wire_feed`).
    """

    def monotonic(self) -> float:
        """Монотонная стрелка, секунды."""

    def sleep(self, seconds: float) -> None:
        """Подождать столько секунд."""
