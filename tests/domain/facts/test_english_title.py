"""Проверяет чтение имени картины из ссылки на английскую статью."""

from tests.articles import page
from torrcast.domain.facts.english_title import english_title


def test_the_english_heading_loses_its_disambiguation_bracket() -> None:
    """«Wednesday (TV series)» - это разметка Википедии; индексер ищет «Wednesday»."""
    assert english_title(page("Уэнздей", "", english="Wednesday (TV series)")) == "Wednesday"
    assert english_title(page("Тачки", "", english="Cars (film)")) == "Cars"
    assert english_title(page("Внутри Лапенко", "")) == ""
