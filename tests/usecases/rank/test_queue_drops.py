"""Счёт отсева по пулу картины: сумма очереди и причин сходится с длиной пула."""

from __future__ import annotations

from dataclasses import dataclass, field

from tests.usecases.rank.releases import RUNTIME, rel
from torrcast.domain.episode import Episode
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.rank.off_season import _buried, _disc, _heavy, _pinned, off_season
from torrcast.usecases.rank.queue_drops import queue_drops


@dataclass
class Plan:
    """Ровно то, что правило у плана и спрашивает."""

    ranked: list[Release] = field(default_factory=list)
    picture: Picture = field(default_factory=lambda: Picture(title="Кино", year=1999))
    off_season: int = 0
    want: Episode | None = None
    runtime: float = RUNTIME
    warn_mbit: float = 20.0
    hard_mbit: float = 0.0
    copy_hevc: bool = False
    last_resort: bool = False


def test_the_count_covers_the_pool_and_the_off_season_part() -> None:
    """🔴 TC-186. На замере между пулом и очередью терялось 895 раздач из 3164."""
    plan = Plan(
        ranked=[rel(name="взятый"), rel(name="Кино BDMV"), rel(name="жирный", size_gb=28)],
        off_season=2,
    )
    counts = queue_drops(plan, [1])

    assert counts == {off_season(): 2, _disc(): 1, _heavy(): 1}
    assert sum(counts.values()) + 1 == len(plan.ranked) + plan.off_season


def test_a_hand_named_release_leaves_the_rest_unasked_not_dropped() -> None:
    plan = Plan(ranked=[rel(name="взятый"), rel(name="Кино BDMV")])
    assert queue_drops(plan, [1], pinned=True) == {_pinned(): 1}


def test_a_queue_that_took_everyone_counts_nothing() -> None:
    plan = Plan(ranked=[rel(name="первый"), rel(name="второй")])
    assert queue_drops(plan, [1, 2]) == {}


def test_a_release_buried_in_this_run_has_its_own_reason() -> None:
    """Очередь пустила бы её, не будь она похоронена: причина - похороны, а не ворота."""
    plan = Plan(ranked=[rel(name="похороненный"), rel(name="взятый")])
    assert queue_drops(plan, [2], buried={1}) == {_buried(): 1}
