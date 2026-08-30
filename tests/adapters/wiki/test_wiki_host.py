"""Проверяет выбор источника справки по языку продукта."""

from torrcast.adapters.wiki.endpoints import WIKI_HOST
from torrcast.adapters.wiki.wiki_host import wiki_host


def test_the_blurb_source_follows_the_product_language() -> None:
    """Под английским языком справка читается из английской Википедии, а не из русской."""
    assert wiki_host("en") == "en.wikipedia.org"
    assert wiki_host("ru") == WIKI_HOST


def test_an_unknown_language_falls_back_to_the_source_that_was_there_before() -> None:
    """Незнакомый язык - не повод остаться без справки: отвечает прежний источник."""
    assert wiki_host("") == WIKI_HOST
    assert wiki_host("de") == WIKI_HOST
