"""Зеркало :mod:`torrcast.domain.facts.kin`: родня картины по её другим частям."""

from torrcast.domain.facts.kin import Kin


def test_two_pictures_of_different_years_are_two_different_kin() -> None:
    """Год входит в значение целиком: два ряда одной картины разных лет - разные записи."""
    assert Kin("Q1", "Крепкий орешек", 1988) != Kin("Q1", "Крепкий орешек", 1990)
    assert Kin("Q1", "Крепкий орешек", 1988) == Kin("Q1", "Крепкий орешек", 1988)


def test_a_picture_without_a_confirmed_year_still_carries_its_name() -> None:
    """Год бывает не сверен вовсе - имя и идентификатор при этом остаются."""
    assert Kin("Q2", "Форсаж 11", None).year is None
    assert Kin("Q2", "Форсаж 11", None).name == "Форсаж 11"
