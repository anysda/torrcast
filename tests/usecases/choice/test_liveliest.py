"""Зеркало :mod:`torrcast.usecases.choice.liveliest`: номер самой живой картины меню.

Список остаётся хронологическим, меняется только цифра в скобках: «моана» печатает
четыре картины и предлагает не немую документалку 1926 года.
"""

from __future__ import annotations

from tests.usecases.choice.world import parts
from torrcast.usecases.choice import liveliest


def test_the_number_points_at_the_liveliest_picture_and_not_at_the_first_one() -> None:
    """Ответ - номер самой живой картины, а список при этом не переупорядочивается."""
    moana = parts(
        ("Моана: романтика золотого века", 1926, 5),
        ("Моана", 2016, 222),
        ("Моана 2", 2024, 140),
    )

    assert liveliest(moana) == 2


def test_an_equal_weight_is_broken_by_chronology_and_not_by_the_order_of_the_list() -> None:
    """Равный вес - берём раннюю: при ничьей хронология и есть ответ.

    Отдай ничью последней - и дефолт прыгал бы на свежий ремейк всякий раз, когда рои
    сравнялись, то есть по причине, которой человек не называл.
    """
    tie = parts(("Человек-невидимка", 1933, 40), ("Человек-невидимка", 2020, 40))

    assert liveliest(tie) == 1


def test_a_menu_where_everything_is_dead_still_gets_a_number_to_point_at() -> None:
    """Живых нет вовсе - цифра в скобках всё равно обязана на что-то указывать."""
    dead = parts(("Кино", 1999, 0), ("Кино", 2001, 0))

    assert liveliest(dead) == 1
