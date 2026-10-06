"""Зеркало :mod:`torrcast.domain.part_of_franchise`: номерованная часть спрошенной франшизы."""

from torrcast.domain.part_of_franchise import part_of_franchise
from torrcast.domain.picture import Picture


def test_a_numbered_part_of_the_asked_franchise_is_its_part() -> None:
    assert part_of_franchise(Picture(title="Брат 2", year=2000, part=2), "брат")


def test_the_original_root_names_the_franchise_too() -> None:
    picture = Picture(title="Тачки 2", year=2011, original="Cars 2", part=2)

    assert part_of_franchise(picture, "cars")


def test_a_numbered_part_of_another_franchise_is_not_a_part_of_the_asked_one() -> None:
    picture = Picture(title="Агашки по вызову 2: Начало", year=2022, part=2)

    assert not part_of_franchise(picture, "начало")


def test_an_unnumbered_picture_is_no_part() -> None:
    assert not part_of_franchise(Picture(title="Брат", year=1997), "брат")
