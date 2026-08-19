"""Тяжесть копии куска: точный вес с диска, а без него - предсказание по карте."""

from __future__ import annotations

from tests.adapters.recode.grids import grid, keys
from torrcast.adapters.recode.oversize import oversize
from torrcast.adapters.recode.weights import Weights


def test_an_oversize_copy_is_judged_by_the_stat_when_there_is_one() -> None:
    """Вес готовой копии известен точно одним ``stat``; без неё судим предсказанием по карте."""
    lines = grid()
    weights = Weights.of(keys(rate=2.0e6), lines)
    assert weights is not None
    cap = 16_000_000

    assert oversize(weights, lines, cap, 0, size=20_000_000), "точный вес выше потолка"
    assert not oversize(weights, lines, cap, 0, size=1_000), "точный вес ниже потолка"
    assert oversize(weights, lines, cap, 0) == (weights.size(0, lines.span(0)) > cap)
