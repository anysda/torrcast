"""Проверяет чтение межъязыкового заголовка статьи - адреса той же картины в чужой вики."""

from tests.articles import page
from torrcast.domain.facts.linked_title import linked_title


def test_the_bracket_stays_because_it_is_part_of_the_address() -> None:
    """Отрежь уточнение - и второй запрос уедет в страницу значений, а не в статью."""
    assert linked_title(page("Уэнздей", "", english="Wednesday (TV series)")) == (
        "Wednesday (TV series)"
    )
    assert linked_title(page("Тачки", "", english="Cars (film)")) == "Cars (film)"


def test_an_article_without_a_link_answers_with_nothing() -> None:
    """Ссылки нет - и адреса нет: справке на этом языке взяться неоткуда."""
    assert linked_title(page("Внутри Лапенко", "")) == ""
