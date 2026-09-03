"""Зеркало :mod:`torrcast.domain.facts.named_year`: год, названный самим именем статьи."""

from torrcast.domain.facts.named_year import named_year


def test_the_year_in_the_qualifier_is_read_and_costs_nothing() -> None:
    """Уточнение в скобке - это подтверждённый год: статья под таким именем нашлась."""
    assert named_year("Паразиты (фильм, 2019)") == 2019
    assert named_year("Матрица (фильм, 1999)  ") == 1999


def test_a_number_that_is_not_a_qualifier_is_not_a_year() -> None:
    """Число из названия годом не считается, иначе «2001» стал бы годом чужой картины."""
    assert named_year("2001: Космическая одиссея") is None
    assert named_year("Матрица (фильм)") is None
    assert named_year("Тачки 2") is None
