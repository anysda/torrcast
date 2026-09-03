"""Зеркало :mod:`torrcast.domain.facts.page_kinds`: род картины по её категориям."""

from torrcast.domain.facts.page_kinds import page_kinds
from torrcast.domain.json_value import JsonValue


def _page(*categories: str) -> JsonValue:
    return {"title": "Паразиты", "categories": [{"title": one} for one in categories]}


def test_a_series_and_a_film_are_told_apart_by_the_same_categories() -> None:
    """«Паразиты» 2019 года - это и фильм, и сериал, и без рода они делили одну картинку."""
    assert page_kinds(_page("Категория:Фильмы 2019 года")) == {"movie"}
    assert page_kinds(_page("Категория:Телесериалы Республики Корея")) == {"tv"}
    assert page_kinds(_page("Категория:Кинокомедии США")) == {"movie"}


def test_categories_that_say_nothing_about_the_kind_leave_it_unsaid() -> None:
    """Несказанное родом не считается: отсев по нему выбросил бы годную статью."""
    assert page_kinds(_page("Категория:Появились в 2019 году")) == set()
    assert page_kinds(None) == set()
