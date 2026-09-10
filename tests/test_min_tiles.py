"""Проверяет min_tiles: планку полноты полок (ТЗ §9) роняет любая из двух."""

from web.min_tiles import FLOOR, min_tiles


def test_the_shortest_of_the_two_shelves_sets_the_count() -> None:
    """Мерой идёт самая короткая полка, а не среднее и не сумма."""
    assert min_tiles({"fresh": list(range(30)), "popular": list(range(18))}) == 18


def test_a_missing_or_empty_shelf_counts_as_zero() -> None:
    """Полки нет в теле вовсе - её счёт ноль, а не «ключа не было, пропустим»."""
    assert min_tiles({"fresh": list(range(30))}) == 0


def test_the_floor_is_the_twenty_tiles_of_the_spec() -> None:
    """Планка - дословные «не меньше 20 плиток» приёмки ТЗ §9."""
    assert FLOOR == 20
