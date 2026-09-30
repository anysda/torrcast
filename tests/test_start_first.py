"""Приговор полки ждёт подъём показа, но не дольше своего срока."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue
from web.start_first import STEP, WITHIN, start_first


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_no_start_underway_costs_the_verdict_nothing() -> None:
    clock = _Clock()

    start_first(lambda: None, clock.sleep, clock)

    assert clock.slept == []


def test_a_verdict_waits_until_the_show_start_is_over() -> None:
    clock, left = _Clock(), [3]

    def seen() -> dict[str, JsonValue] | None:
        left[0] -= 1
        return {"waited": 1.0} if left[0] >= 0 else None

    start_first(seen, clock.sleep, clock)

    assert clock.slept == [STEP] * 3


def test_a_stuck_start_holds_the_verdict_only_until_its_deadline() -> None:
    clock = _Clock()

    start_first(lambda: {"waited": 1.0}, clock.sleep, clock)

    assert WITHIN <= clock.now < WITHIN + STEP * 2
