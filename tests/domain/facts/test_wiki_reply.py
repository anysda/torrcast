"""Проверяет разбор ответа Википедии: обратный путь имён, статьи, склейка пакетов."""

from typing import Any

from tests.articles import CARS, wiki_reply
from torrcast.domain.facts.wiki_reply import _article, _merged, _pages, _ranked


def test_pages_read_the_way_back_from_the_asked_name() -> None:
    """Нормализация и перенаправление приезжают отдельными списками - их и читаем."""
    payload: dict[str, Any] = {
        "query": {
            "normalized": [{"from": "тачки", "to": "Тачки"}],
            "redirects": [{"from": "Тачки", "to": "Тачки (мультфильм)"}],
            "pages": [{"title": "Тачки (мультфильм)", "extract": CARS}],
        }
    }
    hops, pages = _pages(payload)
    assert hops == {"тачки": "Тачки", "Тачки": "Тачки (мультфильм)"}
    assert _article("тачки", hops, pages)["extract"] == CARS


def test_a_disambiguation_and_a_missing_page_are_not_articles() -> None:
    """Страница значений и пустышка статьёй не считаются - на этом стоит вся справка."""
    hops, pages = _pages(wiki_reply())
    assert _article("Моана", hops, pages) is None
    assert _article("Моана 3", hops, pages) is None
    assert _article("Тачки", hops, pages) is not None


def test_answers_of_several_batches_merge_into_one() -> None:
    """Разбор кандидатов о пакетах знать не должен: склеиваются все три списка."""
    one: dict[str, Any] = {"query": {"pages": [{"title": "Тачки"}], "normalized": []}}
    two: dict[str, Any] = {
        "query": {"pages": [{"title": "Моана"}], "redirects": [{"from": "а", "to": "б"}]}
    }
    merged = _merged([one, two, "не словарь"])
    assert [page["title"] for page in merged["query"]["pages"]] == ["Тачки", "Моана"]
    assert merged["query"]["redirects"] == [{"from": "а", "to": "б"}]


def test_search_results_keep_the_order_of_the_search_and_drop_disambiguations() -> None:
    """Порядок выдачи задаёт сам поиск, а страницы значений в него не попадают."""
    payload: dict[str, Any] = {
        "query": {
            "pages": [
                {"title": "второй", "index": 2},
                {"title": "первый", "index": 1},
                {"title": "значения", "index": 0, "pageprops": {"disambiguation": ""}},
            ]
        }
    }
    assert [page["title"] for page in _ranked(payload)] == ["первый", "второй"]
