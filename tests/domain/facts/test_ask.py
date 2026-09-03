"""Зеркало :mod:`torrcast.domain.facts.ask`: чем картину отличают от тёзки."""

from torrcast.domain.facts.ask import Ask


def test_two_films_of_one_name_are_two_different_asks() -> None:
    """Год и род входят в саму просьбу: тёзки не сливаются в одну картину.

    Просьба ездит ключом словаря через весь поход за постером, и совпади она у «Матрицы»
    1999 года с «Матрицей» 2021-го, обе строки списка получили бы одну картинку.
    """
    assert Ask("Матрица", 1999, "movie") != Ask("Матрица", 2021, "movie")
    assert Ask("Паразиты", 2019, "movie") != Ask("Паразиты", 2019, "tv")
    assert len({Ask("Матрица", 1999, "movie"), Ask("Матрица", 1999, "movie")}) == 1


def test_the_original_name_stands_beside_and_does_not_make_another_picture() -> None:
    """Оригинальное имя - подсказка, а не примета: без него просьба та же самая."""
    assert Ask("Матрица", 1999, "movie").original == ""
    assert Ask("Матрица", 1999, "movie", "The Matrix").title == "Матрица"
