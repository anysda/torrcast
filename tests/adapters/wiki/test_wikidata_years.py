"""Проверяет годы выхода пачкой из Wikidata: один запрос на весь список находок."""

from __future__ import annotations

from typing import Any

from tests.fakes.json_client import FakeJsonClient
from torrcast.adapters.wiki.endpoints import WIKIDATA_HOST
from torrcast.adapters.wiki.wikidata_years import WikidataYears


def _reply(*rows: tuple[str, str]) -> dict[str, Any]:
    return {
        "results": {
            "bindings": [
                {
                    "item": {"value": f"http://www.wikidata.org/entity/{entity}"},
                    "date": {"value": date},
                }
                for entity, date in rows
            ]
        }
    }


def test_the_whole_list_is_asked_in_one_request() -> None:
    """🔴 Ради этого запрос и собран пачкой: год стоил бы похода на каждую находку.

    Список обзора ждёт приговор на месте, и десяток отдельных SPARQL превратил бы
    ожидание в секунды перед пустым экраном.
    """
    client = FakeJsonClient(lambda host, path, params: _reply(("Q83495", "1999-03-31")))
    years = WikidataYears(client).years(["Q83495", "Q192724", "Q83495"], 1.0)

    assert years == {"Q83495": {1999}}
    assert len(client.calls) == 1, f"походов в Wikidata {len(client.calls)}"
    assert client.calls[0][0] == WIKIDATA_HOST
    query = client.calls[0][2]["query"]
    assert "wd:Q83495" in query and "wd:Q192724" in query, f"спрошено не про всех: {query}"
    assert query.count("wd:Q83495") == 1, "повтор поехал в запрос дважды"


def test_a_stranger_string_never_reaches_the_body_of_the_query() -> None:
    """🔴 Идентификатор уезжает в ТЕЛО SPARQL: чужой знак в нём - это чужой запрос."""
    client = FakeJsonClient(lambda host, path, params: _reply())
    assert WikidataYears(client).years(["} } INSERT DATA { x", "Q1 ."], 1.0) == {}
    assert client.calls == [], "мусор поехал в Wikidata запросом"


def test_a_refused_network_means_no_year_and_not_a_broken_search() -> None:
    """Несверенный год означает «постера нет», и это честнее постера соседней картины."""

    def refuse(host: str, path: str, params: dict[str, str]) -> Any:
        raise OSError("HTTP 429")

    assert WikidataYears(FakeJsonClient(refuse)).years(["Q83495"], 1.0) == {}


def test_nothing_to_ask_about_costs_nothing() -> None:
    """Пустая просьба не должна стоить похода: у большинства год сверен даром."""
    client = FakeJsonClient(lambda host, path, params: _reply())
    assert WikidataYears(client).years([], 1.0) == {}
    assert client.calls == []


def test_a_series_names_its_year_by_the_start_of_the_broadcast() -> None:
    """🔴 ОТРИЦАТЕЛЬНАЯ ПРОБА на второе свойство: спроси одну публикацию - года нет.

    Живой случай «Дюна» 2000 года: английская статья мини-сериала есть, а даты
    публикации (``P577``) у него в Wikidata нет вовсе - свой год сериал держит
    началом показа (``P580``). Пока спрашивалась одна публикация, год оставался
    несверенным, и мини-сериал терял постер при живой статье.
    """

    def only_the_start(host: str, path: str, params: dict[str, str]) -> Any:
        if "wdt:P580" not in params["query"]:
            return _reply()
        return _reply(("Q987305", "2000-12-03T00:00:00Z"))

    got = WikidataYears(FakeJsonClient(only_the_start)).years(["Q987305"], 1.0)

    assert got == {"Q987305": {2000}}, "у сериала год остался несверенным"


def test_the_date_of_publication_is_still_what_a_film_answers_with() -> None:
    """Второе свойство ДОПИСАНО к первому, а не заменило его: у фильма год тот же."""

    def only_the_publication(host: str, path: str, params: dict[str, str]) -> Any:
        assert "wdt:P577" in params["query"], "публикацию перестали спрашивать вовсе"
        return _reply(("Q83495", "1999-03-31T00:00:00Z"))

    assert WikidataYears(FakeJsonClient(only_the_publication)).years(["Q83495"], 1.0) == {
        "Q83495": {1999}
    }
