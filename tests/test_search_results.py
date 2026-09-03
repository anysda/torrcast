"""Зеркало формы поиска: план круга поиска - контрактный пункт меню с номером ``pick``."""

from __future__ import annotations

from typing import Any, cast

from hass.search_results import search_results
from torrcast.domain.json_value import JsonValue
from torrcast.domain.kind import Kind
from torrcast.domain.picture import Picture
from torrcast.usecases.select.plan import Plan


def _plan(title: str, year: int, kind: Kind = "movie") -> Plan:
    return Plan(
        picture=Picture(title=title, year=year, kind=kind), ranked=[], runtime=0.0, warn_mbit=0.0
    )


def _records(results: list[JsonValue]) -> list[dict[str, Any]]:
    """Записи выдачи под своим видом: договор обещает объекты, а не любой JSON."""
    assert all(isinstance(result, dict) for result in results), "запись выдачи - объект"
    return cast("list[dict[str, Any]]", results)


def test_plans_become_picks_numbered_from_one_in_the_products_own_order() -> None:
    """Оригинальное имя едет полем записи: у части находок русской статьи нет вовсе.

    Пустая строка на его месте - это «продукт про оригинал не знает», и картинку такой
    находке ищут по одному русскому имени.
    """
    plans = [_plan("Тачки", 2006), _plan("Тачки 2", 2011)]

    assert search_results(plans, 2) == [
        {
            "pick": 1,
            "key": "movie:тачки:2006",
            "title": "Тачки",
            "year": 2006,
            "kind": "movie",
            "original": "",
            "default": False,
        },
        {
            "pick": 2,
            "key": "movie:тачки-2:2011",
            "title": "Тачки 2",
            "year": 2011,
            "kind": "movie",
            "original": "",
            "default": True,
        },
    ]


def test_exactly_one_record_is_flagged_default_and_it_is_the_taken_number() -> None:
    """Поле ``default`` - весь договор с карточкой: она ставит помеченный пункт первым."""
    plans = [_plan("Тачки", 2006), _plan("Тачки 2", 2011), _plan("Тачки 3", 2017)]

    for taken in (1, 2, 3):
        records = _records(search_results(plans, taken))
        flagged = [record["pick"] for record in records if record["default"]]

        assert flagged == [taken], f"взятой обязана быть ровно одна запись, номер {taken}"


def test_an_empty_menu_is_an_empty_list_not_a_refusal() -> None:
    """Отказ - забота круга поиска (:mod:`torrcast.usecases.discover.search_circle`);
    пустой список плана этот шаг не сочиняет и не превращает во что-то другое."""
    assert search_results([], 0) == []
