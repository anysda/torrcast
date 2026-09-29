"""Checks that the indexer circle measures every wait from its own start."""

from __future__ import annotations

import time

import pytest

from tests.adapters.prowlarr.test_indexer_circle import _KNABEN, _RUTOR, _circle


@pytest.mark.machine
def test_a_silent_core_indexer_costs_its_budget_not_the_neighbours_answer_on_top() -> None:
    circle, _http = _circle(rows=2, delay={1: 0.3, 2: 0.9})
    began = time.monotonic()
    got, _error = circle.run([_KNABEN, _RUTOR], "матрица", 100)
    elapsed = time.monotonic() - began
    assert [len(batch) for batch in got] == [2]
    assert circle.lost == ["RuTor"]
    assert elapsed < 0.75, f"circle held {elapsed:.2f} s: 0.3 s answer plus a full budget"
    assert len(circle.late(wait=2.0)) == 2, "the late answer still lands in the top-up"
