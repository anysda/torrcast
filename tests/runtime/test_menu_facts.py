"""Справка меню на действующих адаптерах: тот же сценарий, только уже проведённый."""

from __future__ import annotations

from tests.articles import MOANA
from torrcast.domain.facts.fact import Fact
from torrcast.runtime.facts_wiring import FACTS
from torrcast.runtime.menu_facts import MenuFacts
from torrcast.usecases.facts import Facts

MOANA_KEY = ("Моана", 2016)


def test_the_menu_reference_is_the_scenario_on_the_process_wiring() -> None:
    """Второго сценария здесь нет - есть тот же, с кэшем и источником всего процесса."""
    facts = MenuFacts([MOANA_KEY], budget=0.0)

    assert isinstance(facts, Facts)
    assert facts.store is FACTS.cache
    assert facts.source is FACTS.blurbs
    assert facts.wanted == [MOANA_KEY]
    assert facts.budget == 0.0


def test_a_franchise_already_in_the_cache_never_walks_anywhere() -> None:
    """Второй показ той же франшизы мгновенный: сети на этом пути нет вовсе."""
    FACTS.cache.remember({MOANA_KEY: Fact(about=MOANA, rating="IMDb 7.6")})

    facts = MenuFacts([MOANA_KEY], budget=0.0)
    facts.start()

    assert facts.get(*MOANA_KEY) == Fact(about=MOANA, rating="IMDb 7.6")


def test_without_a_budget_the_menu_is_not_held_up() -> None:
    """Бюджет по умолчанию берётся общий, а названный - уважается."""
    assert MenuFacts([MOANA_KEY]).budget > 0.0
    assert MenuFacts([MOANA_KEY], 0.25).budget == 0.25
