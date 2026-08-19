"""Зеркало пустого счёта опоздавших: план собран не поиском, и ждать ему некого."""

from __future__ import annotations

from tests.usecases.select.world import plan
from torrcast.usecases.select._nobody_waiting import _nobody_waiting


def test_a_plan_built_outside_the_search_waits_for_nobody() -> None:
    """Умолчание плана - именно этот счёт: звать его безопасно всегда."""
    assert plan().waiting is _nobody_waiting
    assert plan().waiting() == ()
