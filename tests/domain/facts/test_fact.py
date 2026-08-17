"""Проверяет модель справки по одной картине."""

from torrcast.domain.facts.fact import Fact


def test_an_empty_fact_is_falsy_and_any_filled_field_makes_it_true() -> None:
    """Пустые поля — норма: нет данных, значит нет строки в меню."""
    assert not Fact()
    assert Fact(about="о гонках")
    assert Fact(rating="IMDb 7.2")
    assert Fact(runtime="1 ч 56 мин")


def test_a_fact_is_compared_by_its_fields() -> None:
    """Справка - значение, а не объект: два одинаковых факта равны."""
    assert Fact(about="о гонках", rating="IMDb 7.2") == Fact(about="о гонках", rating="IMDb 7.2")
