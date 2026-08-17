"""Проверяет поиск тёзки того же года среди статей одного ответа."""

from typing import Any

from tests.articles import NINE_CARTOON, NINE_MUSICAL
from torrcast.domain.facts.namesake import namesake


def test_the_second_picture_of_the_same_year_is_named() -> None:
    """🔴 TC-371. Имя и год совпали у двух картин - развести их разбору нечем."""
    pages: list[Any] = [
        {"title": "Девять (фильм)", "extract": NINE_MUSICAL},
        {"title": "9 (мультфильм, 2009)", "extract": NINE_CARTOON},
    ]
    assert namesake(pages, "Девять (фильм)", 2009) == "9 (мультфильм, 2009)"


def test_a_namesake_is_not_read_from_a_non_cinema_article() -> None:
    """Тёзка обязана быть КАРТИНОЙ: под «Матрицей» лежит ещё и таблица."""
    pages: list[Any] = [
        {"title": "Девять (фильм)", "extract": NINE_MUSICAL},
        {
            "title": "9 (число)",
            "extract": "9 (девять) — натуральное число между 8 и 10, известное с 2009 года.",
        },
    ]
    assert namesake(pages, "Девять (фильм)", 2009) == ""


def test_without_a_year_there_is_nothing_to_compare() -> None:
    """Год неизвестен - и двусмысленности не видно: говорить не о чем."""
    assert namesake([{"title": "Девять (фильм)", "extract": NINE_MUSICAL}], "9", None) == ""
