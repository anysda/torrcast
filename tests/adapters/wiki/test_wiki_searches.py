"""Проверяет поиск статьи, когда прямые заголовки не назвали её."""

from typing import Any

from tests.fakes.json_client import FakeJsonClient
from torrcast.adapters.wiki.wiki_searches import wiki_searches


def test_search_keeps_the_matched_russian_heading_and_answers_the_picture() -> None:
    """English catalogue name reaches the localized article through its original title."""
    key = ("Mary and Max", 2009)
    about = "«Мэри и Макс» (англ. Mary and Max) — австралийский фильм 2009 года."

    def answer(_host: str, _path: str, params: dict[str, str]) -> Any:
        assert params["gsrsearch"] == "Mary and Max фильм"
        return {
            "query": {
                "pages": [
                    {
                        "title": "Мэри и Макс",
                        "extract": about,
                        "index": 1,
                        "pageprops": {"wikibase_item": "Q191845"},
                    }
                ]
            }
        }

    found, replies, answered = wiki_searches(FakeJsonClient(answer), [key], 1.0, {key: "movie"})

    assert found == {key: ["Мэри и Макс"]}
    assert len(replies) == 1
    assert answered == {key}
