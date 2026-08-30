"""Зеркало бюджета справки на втором заходе: отмены по бюджету у добора нет."""

from __future__ import annotations

import pytest

from tests.usecases.discover.world import Indexer, Said, franchise, row
from torrcast.domain.facts.settings import FACTS_BUDGET
from torrcast.domain.goal_spare import CIRCLE_SHARE
from torrcast.usecases.discover._second_budget import _second_budget


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русская строка о боданном бюджете добора."""


_FOUND = franchise("психо", [row("Психо / Psycho (1960) BDRip 1080p")])


def test_a_picture_already_found_leaves_the_facts_their_usual_ceiling() -> None:
    """Картина есть - справка тут не единственная опора, и потолок у неё обычный."""
    assert _second_budget(Indexer(spare=9.0), "психо", _FOUND, Said()) == FACTS_BUDGET


def test_an_empty_find_gives_the_facts_the_whole_spare() -> None:
    """🔴 TC-243. Картины не нашлось вовсе - справке отдают весь остаток за вычетом круга."""
    assert _second_budget(Indexer(spare=9.0), "психо", [], Said()) == 9.0 - CIRCLE_SHARE


def test_a_spent_goal_does_not_cancel_the_top_up() -> None:
    """🔴 TC-386. Остатка нет - добор всё равно делается, и человек читает про это строку."""
    said = Said()

    assert _second_budget(Indexer(spare=0.1), "тачки", _FOUND, said) == FACTS_BUDGET
    assert "всё равно делаю" in said.text
    assert "картину ищут оба её имени" in said.text
