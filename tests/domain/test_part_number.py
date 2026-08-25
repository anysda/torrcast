"""Зеркало :mod:`torrcast.domain.part_number`: номер части, взятый из названия."""

from torrcast.domain.part_number import part_number


def test_a_number_at_the_end_of_the_title_is_the_number_of_the_part() -> None:
    assert part_number("Брат 2") == 2


def test_a_roman_number_counts_the_same() -> None:
    assert part_number("Рокки IV") == 4


def test_a_title_without_a_number_has_no_part() -> None:
    assert part_number("Брат") is None


def test_a_range_of_numbers_is_not_a_part() -> None:
    """«1-2» - это сборник из двух частей, а не вторая часть."""
    assert part_number("Брат 1-2") is None
