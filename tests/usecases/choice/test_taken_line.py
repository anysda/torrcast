"""Зеркало :mod:`torrcast.usecases.choice.taken_line`: строка про взятое без вопроса.

Решение принято за человека, поэтому строка обязана и назвать картину, и дать ход к
любой другой.
"""

from __future__ import annotations

from tests.usecases.choice.world import parts
from torrcast.usecases.choice.taken_line import taken_line


def test_the_line_names_the_picture_the_count_and_the_way_to_any_other() -> None:
    """Три вещи в одной строке: что взято, из скольких и чем назвать другое."""
    cars = parts(("Тачки", 2006, 66), ("Тачки 2", 2011, 71), ("Тачки 3", 2017, 121))

    assert taken_line(cars, 1, "тачки") == (
        "беру «Тачки (2006)» - подошло картин 3; другая: cast releases тачки и --pick N"
    )


def test_a_series_is_named_a_series_so_the_two_kinds_are_not_confused() -> None:
    """Сериал и одноимённый фильм в строке различимы: подпись картины та же, что в меню."""
    vikings = [*parts(("Викинги", 1958, 90)), *parts(("Викинги", 2013, 90))]
    vikings[1].picture.kind = "tv"

    assert taken_line(vikings, 2, "викинги") == (
        "беру «Викинги (2013, сериал)» - подошло картин 2; другая: cast releases викинги и --pick N"
    )
