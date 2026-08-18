"""Зеркало пустого долива: план собран не поиском, и опоздавших у него не бывает."""

from __future__ import annotations

from tests.usecases.select.world import plan
from torrcast.usecases.select._nothing_late import _nothing_late


def test_a_plan_built_outside_the_search_has_nothing_to_top_up() -> None:
    """Умолчание плана - именно этот долив: звать его безопасно всегда."""
    assert plan().late is _nothing_late
    assert plan().late() == []
