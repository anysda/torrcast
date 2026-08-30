"""Зеркало :mod:`torrcast.usecases.choice.head_line`: строка одного пункта меню.

Ту же строку собирает и первая печать меню, и дописывание украшений в неё же.
"""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.facts.fact import Fact
from torrcast.domain.picture import Picture
from torrcast.usecases.choice.head_line import head_line

CARS = Picture(title="Тачки", year=2006, kind="movie", part=1, original=None, releases=[])


def test_the_number_the_title_and_the_year_are_the_whole_line_without_a_reference() -> None:
    """Справки нет - строка ровно та же, что была бы без неё: ни разделителей, ни признаний."""
    assert head_line(1, CARS, Fact()) == "  1. Тачки (2006)"


def test_the_rating_and_the_runtime_stand_in_the_same_line_as_the_title() -> None:
    """Украшения дописываются в ту же строку: глаз идёт по номерам, а не по колонкам."""
    line = head_line(2, CARS, Fact(rating="IMDb 7.1", runtime="1 ч 57 мин"))

    assert line == "  2. Тачки (2006) · IMDb 7.1 · 1 ч 57 мин"


def test_only_the_half_that_arrived_is_added_to_the_line() -> None:
    """Приехала половина справки - в строку встаёт она одна, без пустого разделителя."""
    assert head_line(1, CARS, Fact(rating="IMDb 7.1")) == "  1. Тачки (2006) · IMDb 7.1"
    assert head_line(1, CARS, Fact(runtime="1 ч 57 мин")) == "  1. Тачки (2006) · 1 ч 57 мин"


def test_a_picture_standing_outside_the_numbered_line_says_so_in_its_line() -> None:
    """Пункт без номера части уезжает вниз списка и говорит, почему он там."""
    assert head_line(3, CARS, Fact(), aside=True) == (
        f"  3. Тачки (2006{phrase('choice.no_part_mark')})"
    )
