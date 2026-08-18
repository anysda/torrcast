"""Зеркало :mod:`torrcast.domain.facts.wiki_pages`: обратный путь имён и статьи ответа."""

from typing import Any

from tests.articles import CARS, wiki_reply
from torrcast.domain.facts.wiki_pages import wiki_pages
from torrcast.domain.facts.wiki_reply import _article


def test_pages_read_the_way_back_from_the_asked_name() -> None:
    """Нормализация и перенаправление приезжают отдельными списками - их и читаем."""
    payload: dict[str, Any] = {
        "query": {
            "normalized": [{"from": "тачки", "to": "Тачки"}],
            "redirects": [{"from": "Тачки", "to": "Тачки (мультфильм)"}],
            "pages": [{"title": "Тачки (мультфильм)", "extract": CARS}],
        }
    }
    hops, pages = wiki_pages(payload)
    assert hops == {"тачки": "Тачки", "Тачки": "Тачки (мультфильм)"}
    found = _article("тачки", hops, pages)
    assert found is not None and found["extract"] == CARS


def test_a_disambiguation_and_a_missing_page_are_not_articles() -> None:
    """Страница значений и пустышка статьёй не считаются - на этом стоит вся справка."""
    hops, pages = wiki_pages(wiki_reply())
    assert _article("Моана", hops, pages) is None
    assert _article("Моана 3", hops, pages) is None
    assert _article("Тачки", hops, pages) is not None
