"""Зеркало формы поиска: план круга поиска - контрактный пункт меню с номером ``pick``."""

from __future__ import annotations

from typing import Any, cast

from hass.search_results import search_results
from torrcast.domain.json_value import JsonValue
from torrcast.domain.kind import Kind
from torrcast.domain.picture import Picture
from torrcast.usecases.select.plan import Plan


def _plan(title: str, year: int, kind: Kind = "movie", original: str = "") -> Plan:
    return Plan(
        picture=Picture(title=title, year=year, kind=kind, original=original or None),
        ranked=[],
        runtime=0.0,
        warn_mbit=0.0,
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
            "shown": "Тачки",
            "year": 2006,
            "kind": "movie",
            "original": "",
            "default": False,
        },
        {
            "pick": 2,
            "key": "movie:тачки-2:2011",
            "title": "Тачки 2",
            "shown": "Тачки 2",
            "year": 2011,
            "kind": "movie",
            "original": "",
            "default": True,
        },
    ]


def test_the_name_a_person_reads_is_the_one_the_product_speaks(_english: None) -> None:
    """Подпись находки решает продукт, а не карточка: под EN картину зовут оригиналом.

    Ровно тем же правилом её зовёт меню ``cast`` того же серва
    (:func:`torrcast.domain.spoken_title.spoken_title`). Без готового поля один запрос на
    одном стенде давал человеку две выдачи: карточка звала картину «Назад в будущее»,
    пока меню звало её ``Back to the Future``.
    """
    plans = [_plan("Назад в будущее", 1985, original="Back to the Future")]

    assert _records(search_results(plans, 1))[0]["shown"] == "Back to the Future"


def test_a_picture_without_an_english_name_keeps_its_own(_english: None) -> None:
    """Английского имени нет вовсе - подписью остаётся СОБСТВЕННОЕ имя картины.

    Ни пустоты, ни транслита: выбрать пункт, у которого нет имени, человек не может.
    """
    plans = [_plan("Ёлки", 2010)]

    assert _records(search_results(plans, 1))[0]["shown"] == "Ёлки"


def test_under_russian_the_card_is_answered_in_russian(_russian_product: None) -> None:
    """Другая ветка того же правила: язык продукта русский - и подпись русская."""
    plans = [_plan("Назад в будущее", 1985, original="Back to the Future")]

    assert _records(search_results(plans, 1))[0]["shown"] == "Назад в будущее"


def test_the_raw_name_stays_in_the_record_because_the_poster_is_looked_up_by_it(
    _english: None,
) -> None:
    """Подпись подменять ``title`` не вправе: по нему находке ищут картинку.

    :func:`hass.hit_ask._about` строит по этому полю просьбу о постере, а она спрашивает
    РУССКИЙ раздел Википедии и кладёт найденное на общую с карточкой плеера полку
    (:func:`hass.poster_name.poster_name`). Английское имя в ``title`` увело бы поиск не
    туда, а на полке завело бы вторую запись про ту же картину.
    """
    plans = [_plan("Назад в будущее", 1985, original="Back to the Future")]
    record = _records(search_results(plans, 1))[0]

    assert record["title"] == "Назад в будущее"
    assert record["original"] == "Back to the Future"


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
