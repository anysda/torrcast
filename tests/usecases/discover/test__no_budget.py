"""Зеркало охранника дешёвого добора: остаток цели, частный бюджет и отказ за целью."""

from __future__ import annotations

from tests.usecases.discover.world import Indexer, Said
from torrcast.domain.facts.settings import FACTS_BUDGET
from torrcast.domain.goal_spare import CIRCLE_SHARE, SECOND_LEAST
from torrcast.usecases.discover._no_budget import _no_budget


def test_a_healthy_goal_leaves_the_top_up_its_usual_ceiling() -> None:
    """Остатка цели вдоволь - справке достаётся её обычный потолок."""
    assert _no_budget(Indexer(spare=9.0), "добор по «кино»", Said()) == FACTS_BUDGET


def test_the_spare_is_shared_with_the_circle_that_follows_the_facts() -> None:
    """Справка не съедает то, на что рассчитывает сам круг (:data:`CIRCLE_SHARE`).

    Порог захода (:data:`SECOND_LEAST`) ровно из этих двух долей и сложен: справка со
    своим потолком плюс доля круга. Пока остаток не ниже порога, обе доли помещаются.
    """
    assert SECOND_LEAST == FACTS_BUDGET + CIRCLE_SHARE
    assert _no_budget(Indexer(spare=SECOND_LEAST), "добор по «кино»", Said()) == FACTS_BUDGET


def test_the_private_budget_past_the_goal_is_given_once() -> None:
    """🔴 Частный бюджет за съеденной целью выдаётся ОДИН раз за поиск, а не каждому."""
    client = Indexer(spare=0.1)
    said = Said()

    first = _no_budget(client, "добор по «кино»", said)
    second = _no_budget(client, "добор сезона 2", said)

    assert first == FACTS_BUDGET, "первый заход за целью всё равно делается"
    assert second is None, "второй на той же съеденной цели удваивал бы превышенное"
    assert client.over_goal is True
    assert "всё равно делаю" in said.text and "не делаю" in said.text
