"""Таблица фаз старта: время от нуля, цена каждой фазы и выбор самого нуля."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue
from torrcast.domain.report import report


def _marks() -> list[dict[str, JsonValue]]:
    """Три фазы подряд: ответы, юнит, картинка."""
    return [
        {"at": 100.0, "name": "ответы", "pid": 1},
        {"at": 101.5, "name": "юнит", "pid": 1},
        {"at": 104.0, "name": "картинка", "pid": 2},
    ]


def test_an_empty_tape_says_so_instead_of_drawing_a_table() -> None:
    """Меток нет - так и сказано: пустая таблица прочиталась бы как «старт мгновенный»."""
    assert report([]) == "no marks"


def test_the_zero_is_the_named_mark_and_the_cost_is_the_step() -> None:
    """Ноль - названная метка, а цена фазы - шаг от предыдущей, а не от нуля."""
    lines = report(_marks(), zero="ответы").splitlines()

    assert "картинка" in lines[3]
    assert "+4.00" in lines[3], "от нуля - четыре секунды"
    assert "2.50" in lines[3], "а стоила фаза две с половиной"


def test_without_the_named_zero_the_first_mark_becomes_one() -> None:
    """Названной метки в ленте может не быть - тогда ноль берётся с первой."""
    lines = report(_marks(), zero="такой-метки-нет").splitlines()

    assert "+0.00" in lines[1], "первая метка и есть ноль"
