"""Счёт отсева по пулу картины: сумма очереди и причин сходится с длиной пула."""

from __future__ import annotations

from dataclasses import dataclass, field

from tests.usecases.rank.releases import RUNTIME, rel
from torrcast.domain.episode import Episode
from torrcast.domain.release import Release
from torrcast.usecases.rank.drop_reasons import _DISC, _HEAVY, _PINNED, OFF_SEASON
from torrcast.usecases.rank.queue_drops import queue_drops


@dataclass
class _Plan:
    """Ровно то, что правило у плана и спрашивает."""

    ranked: list[Release] = field(default_factory=list)
    off_season: int = 0
    want: Episode | None = None
    runtime: float = RUNTIME
    warn_mbit: float = 20.0
    hard_mbit: float = 0.0
    copy_hevc: bool = False
    last_resort: bool = False


def test_the_count_covers_the_pool_and_the_off_season_part() -> None:
    """🔴 TC-186. На замере между пулом и очередью терялось 895 раздач из 3164."""
    plan = _Plan(
        ranked=[rel(name="взятый"), rel(name="Кино BDMV"), rel(name="жирный", size_gb=28)],
        off_season=2,
    )
    counts = queue_drops(plan, [1])

    assert counts == {OFF_SEASON: 2, _DISC: 1, _HEAVY: 1}
    assert sum(counts.values()) + 1 == len(plan.ranked) + plan.off_season


def test_a_hand_named_release_leaves_the_rest_unasked_not_dropped() -> None:
    plan = _Plan(ranked=[rel(name="взятый"), rel(name="Кино BDMV")])
    assert queue_drops(plan, [1], pinned=True) == {_PINNED: 1}


def test_a_queue_that_took_everyone_counts_nothing() -> None:
    plan = _Plan(ranked=[rel(name="первый"), rel(name="второй")])
    assert queue_drops(plan, [1, 2]) == {}
