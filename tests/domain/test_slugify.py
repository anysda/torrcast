"""Зеркало :mod:`torrcast.domain.slugify`: имя, приведённое к сравнимому виду."""

from torrcast.domain.slugify import slugify


def test_two_ways_of_writing_one_name_give_one_slug() -> None:
    """Регистр, знаки и пробелы у трекеров разные, а картина за ними одна."""
    assert slugify("Брат 2") == slugify("  БРАТ, 2!  ") == "брат-2"


def test_the_letter_yo_is_written_the_way_it_is_usually_typed() -> None:
    """Имя набирают без «ё», и запрос обязан находить раздачу, написанную с ней."""
    assert slugify("Ёлки") == slugify("Елки")


def test_a_name_of_nothing_but_marks_gives_an_empty_slug() -> None:
    assert slugify(" -- ") == ""
