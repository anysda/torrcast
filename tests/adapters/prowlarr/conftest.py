"""Virtual time for the circle's waits: answers land at set seconds, not when a thread wakes."""

from __future__ import annotations

import heapq
import itertools
import math
import threading
from collections.abc import Callable, Iterator

import pytest

from torrcast.adapters.prowlarr import circle_wait as circle_wait_module
from torrcast.adapters.prowlarr.spawn_ask import _Ask


class VirtualTime:
    """One thread plays every answer: a wait moves the clock to the next answer or its end.

    Timers started before the circle's ``began`` let a loaded machine eat the seconds a test
    measured, so its own bounds failed on a circle that waited right.
    """

    def __init__(self) -> None:
        self.now = 0.0
        self._due: list[tuple[float, int, Callable[[], None]]] = []
        self._order = itertools.count()

    def monotonic(self) -> float:
        return self.now

    def at(self, after: float, then: Callable[[], None]) -> None:
        heapq.heappush(self._due, (self.now + after, next(self._order), then))

    def ask(self, name: str, budget: float) -> _Ask:
        ask = _Ask(name, budget)
        ask.done = _Done(self)
        return ask

    def wait(self, done: threading.Event, timeout: float | None) -> bool:
        until = math.inf if timeout is None else self.now + timeout
        while not done.is_set() and self._due and self._due[0][0] <= until:
            when, _, then = heapq.heappop(self._due)
            self.now = max(self.now, when)
            then()
        if not done.is_set() and until != math.inf:
            self.now = max(self.now, until)
        return done.is_set()


class _Done(threading.Event):
    def __init__(self, clock: VirtualTime) -> None:
        super().__init__()
        self._clock = clock

    def wait(self, timeout: float | None = None) -> bool:
        return self._clock.wait(self, timeout)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[VirtualTime]:
    virtual = VirtualTime()
    monkeypatch.setattr(circle_wait_module, "time", virtual)
    yield virtual
