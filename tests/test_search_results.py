"""Зеркало формы поиска: план круга поиска - контрактный пункт меню с номером ``pick``."""

from __future__ import annotations

from hass.search_results import search_results
from torrcast.domain.kind import Kind
from torrcast.domain.picture import Picture
from torrcast.usecases.select.plan import Plan


def _plan(title: str, year: int, kind: Kind = "movie") -> Plan:
    return Plan(
        picture=Picture(title=title, year=year, kind=kind), ranked=[], runtime=0.0, warn_mbit=0.0
    )


def test_plans_become_picks_numbered_from_one_in_the_products_own_order() -> None:
    plans = [_plan("Тачки", 2006), _plan("Тачки 2", 2011)]

    assert search_results(plans) == [
        {"pick": 1, "key": "movie:тачки:2006", "title": "Тачки", "year": 2006, "kind": "movie"},
        {
            "pick": 2,
            "key": "movie:тачки-2:2011",
            "title": "Тачки 2",
            "year": 2011,
            "kind": "movie",
        },
    ]


def test_an_empty_menu_is_an_empty_list_not_a_refusal() -> None:
    """Отказ - забота круга поиска (:mod:`torrcast.usecases.discover.search_circle`);
    пустой список плана этот шаг не сочиняет и не превращает во что-то другое."""
    assert search_results([]) == []
