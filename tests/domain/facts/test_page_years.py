"""Зеркало :mod:`torrcast.domain.facts.page_years`: годы из категорий статьи."""

from torrcast.domain.facts.page_years import page_years
from torrcast.domain.json_value import JsonValue


def _page(*categories: str) -> JsonValue:
    return {"title": "Паразиты", "categories": [{"title": one} for one in categories]}


def test_the_year_is_read_from_any_category_that_names_it() -> None:
    """Форма категории гуляет, и год читается из любой, где стоит рядом со словом «год»."""
    assert page_years(_page("Категория:Фильмы 2019 года")) == {2019}
    assert page_years(_page("Категория:Телесериалы США, запущенные в 2008 году")) == {2008}
    assert page_years(_page("Категория:Аниме 2003 года", "Категория:Фильмы 2004 года")) == {
        2003,
        2004,
    }


def test_a_number_without_the_word_year_is_not_a_year() -> None:
    """Иначе годом стало бы число из названия чужой картины, и сверка пропускала бы соседку."""
    assert page_years(_page("Категория:2001: Космическая одиссея")) == set()


def test_a_page_that_says_nothing_says_nothing_and_not_no() -> None:
    """Пустота тут значит «сказать нечем»: решает про такую статью уже Wikidata."""
    assert page_years(_page()) == set()
    assert page_years(None) == set()
