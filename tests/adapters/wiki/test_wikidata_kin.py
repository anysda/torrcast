"""Родня картины собирается MediaWiki API, не медленным WDQS."""

from typing import Any

import pytest

from tests.fakes.json_client import FakeJsonClient
from torrcast.adapters.wiki.endpoints import WIKIDATA_API_HOST
from torrcast.adapters.wiki.wikidata_kin import WikidataKin
from torrcast.domain.facts.kin import Kin


def _claim(item: str) -> dict[str, Any]:
    return {"mainsnak": {"datavalue": {"value": {"id": item}}}}


def _record(name: str, year: str) -> dict[str, Any]:
    return {
        "labels": {"ru": {"value": name}},
        "claims": {"P577": [{"mainsnak": {"datavalue": {"value": year}}}]},
    }


def test_a_franchise_answers_with_claims_search_and_entity_batches() -> None:
    """Один API-search выдаёт QID, имена и даты берёт одна пачка до 50 штук."""

    def answer(_host: str, _path: str, params: dict[str, str]) -> Any:
        if params["action"] == "wbgetentities" and params["ids"] == "Q105598":
            return {"entities": {"Q105598": {"claims": {"P179": [_claim("Q42")]}}}}
        if params["action"] == "query":
            assert params["srsearch"] == "haswbstatement:P179=Q42"
            return {"query": {"search": [{"title": "Q105598"}, {"title": "Q105993"}]}}
        return {"entities": {"Q105993": _record("Крепкий орешек 2", "+1990-07-04T00:00:00Z")}}

    client = FakeJsonClient(answer)
    assert WikidataKin(client).kin("Q105598", 1.0) == [Kin("Q105993", "Крепкий орешек 2", 1990)]
    assert [call[0] for call in client.calls] == [WIKIDATA_API_HOST] * 3
    assert client.calls[-1][2]["ids"] == "Q105993"
    assert client.calls[-1][2]["props"] == "labels|claims"


def test_a_direct_franchise_claim_is_looked_up_by_its_own_property() -> None:
    def answer(_host: str, _path: str, params: dict[str, str]) -> Any:
        if params["action"] == "wbgetentities" and params["ids"] == "Q1":
            return {"entities": {"Q1": {"claims": {"P8345": [_claim("Q2")]}}}}
        if params["action"] == "query":
            assert params["srsearch"] == "haswbstatement:P8345=Q2"
            return {"query": {"search": [{"title": "Q3"}]}}
        return {"entities": {"Q3": _record("Часть", "+2001-01-01T00:00:00Z")}}

    assert WikidataKin(FakeJsonClient(answer)).kin("Q1") == [Kin("Q3", "Часть", 2001)]


def test_a_stranger_string_never_reaches_the_api() -> None:
    client = FakeJsonClient()
    assert WikidataKin(client).kin("} } INSERT DATA { x", 1.0) == []
    assert client.calls == []


def test_a_refused_network_is_told_apart_from_a_franchise_without_kin() -> None:
    def refuse(_host: str, _path: str, _params: dict[str, str]) -> Any:
        raise OSError("HTTP 429")

    with pytest.raises(OSError, match="HTTP 429"):
        WikidataKin(FakeJsonClient(refuse)).kin("Q105598", 1.0)


def test_a_picture_without_a_franchise_answers_with_an_empty_shelf() -> None:
    client = FakeJsonClient(lambda *_args: {"entities": {"Q1": {"claims": {}}}})
    assert WikidataKin(client).kin("Q1", 1.0) == []
