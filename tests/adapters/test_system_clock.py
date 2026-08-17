"""Настоящие часы: монотонные секунды идут вперёд, стенные подписывают метки."""

from __future__ import annotations

from torrcast.adapters.system_clock import SystemClock
from torrcast.ports.clock import Clock


def test_the_real_clock_satisfies_the_port() -> None:
    """Боевые часы подставляются туда же, куда тестовые: договор один."""
    clock: Clock = SystemClock()

    assert clock.monotonic() > 0
    assert clock.wall() > 1_600_000_000, "стенное время - настоящее, а не с нуля"


def test_sleeping_moves_the_monotonic_clock_forward() -> None:
    """Сон меряется теми же часами, которыми потом считают выдержку."""
    clock = SystemClock()
    before = clock.monotonic()

    clock.sleep(0.01)

    assert clock.monotonic() >= before + 0.005
