"""Зеркало :mod:`torrcast.domain.facts.wiki_ranked`: порядок выдачи поиска Википедии."""

from typing import Any

from torrcast.domain.facts.wiki_ranked import wiki_ranked
from torrcast.domain.json_map import json_map


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
    assert [json_map(page)["title"] for page in wiki_ranked(payload)] == ["первый", "второй"]
