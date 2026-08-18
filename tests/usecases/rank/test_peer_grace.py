"""Сколько раздаче даётся на первый контакт роя: отсрочка платится ценой ошибки."""

from __future__ import annotations

from dataclasses import dataclass, field

from tests.usecases.rank.releases import rel
from torrcast.domain.rank_settings import PEER_GRACE, STEP_GRACE
from torrcast.domain.release import Release
from torrcast.usecases.rank.peer_grace import peer_grace


@dataclass
class Plan:
    """Ровно то, что правило у плана и спрашивает."""

    ranked: list[Release] = field(default_factory=list)


def test_the_long_grace_goes_to_the_one_whose_slip_costs_a_step() -> None:
    """🔴 TC-387. Живой 1080p уступал 720p не своим роем, а нашим нетерпением."""
    plan = Plan([rel(name="полный", quality="1080p"), rel(name="обычный", quality="720p")])
    assert peer_grace(plan, 1, [1, 2]) == STEP_GRACE
    assert peer_grace(plan, 2, [1, 2]) == PEER_GRACE


def test_a_silent_name_stands_with_the_low_ones() -> None:
    """Подтвердить его нечем, пока раздачу не подняли: защищать ступень есть от кого."""
    quiet = rel(name="молчит про кадр", quality=None)
    plan = Plan([rel(name="полный", quality="1080p"), quiet])
    assert peer_grace(plan, 1, [1, 2]) == STEP_GRACE


def test_without_a_step_below_the_grace_is_the_usual_one() -> None:
    plan = Plan([rel(name="полный", quality="1080p"), rel(name="второй", quality="1080p")])
    assert peer_grace(plan, 1, [1, 2]) == PEER_GRACE


def test_only_the_untried_tail_of_the_actual_queue_counts() -> None:
    plan = Plan([rel(name="полный", quality="1080p"), rel(name="обычный", quality="720p")])
    assert peer_grace(plan, 1, [1]) == PEER_GRACE, "--release N"
    assert peer_grace(plan, 1, [2, 1]) == PEER_GRACE, "осуждённый сосед уже позади"
