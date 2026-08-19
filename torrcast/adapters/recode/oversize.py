"""Тяжелее ли копия куска потолка приёмника: наружу такую отдавать нельзя.

Спрашивают его выкладка сегментов и состояние кодировщика."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.adapters.recode.weights import Weights
    from torrcast.adapters.stream_pack.grid import Grid


def oversize(weights: Weights, grid: Grid, cap: int, slot: int, size: int = 0) -> bool:
    """Копия этого куска тяжелее потолка, то есть наружу её отдавать нельзя.

    ``size`` — вес копии, уже лежащей на диске
    (:meth:`torrcast.adapters.stream_pack.packer.Packer.publish` знает его точно, один ``stat``);
    ноль — копии ещё нет, берём предсказание по карте (:meth:`Weights.size`), оно завышает на 12
    % и промахивается в безопасную сторону.
    """
    if size > 0:
        return size > cap
    return weights.size(slot, grid.span(slot)) > cap
