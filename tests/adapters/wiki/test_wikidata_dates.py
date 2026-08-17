"""Проверяет второй источник года: дата первой публикации из Wikidata (P577)."""

from typing import Any

from tests.fakes.json_client import FakeJsonClient
from torrcast.adapters.wiki.endpoints import _WIKIDATA_HOST
from torrcast.adapters.wiki.wikidata_dates import WikidataDates


def test_the_earliest_release_date_becomes_the_year() -> None:
    """Дат у P577 бывает несколько - берём самую раннюю: она и есть «первая публикация»."""
    payload: dict[str, Any] = {
        "results": {
            "bindings": [
                {"date": {"value": "2016-12-02T00:00:00Z"}},
                {"date": {"value": "2016-11-14T00:00:00Z"}},
            ]
        }
    }
    client = FakeJsonClient(lambda host, path, params: payload)

    assert WikidataDates(client).published("Q2", 1.0) == 2016
    host, _path, params = client.calls[0]
    assert host == _WIKIDATA_HOST
    assert "wd:Q2 wdt:P577" in params["query"], "спрашиваем ровно про эту картину"


def test_a_picture_without_a_date_answers_none() -> None:
    """Нет даты - года нет, и это законный исход, а не сбой."""
    client = FakeJsonClient(lambda host, path, params: {"results": {"bindings": []}})

    assert WikidataDates(client).published("Q9", 1.0) is None
