"""Проверяет родню картины из Wikidata: другие части той же франшизы."""

from typing import Any

import pytest

from tests.fakes.json_client import FakeJsonClient
from torrcast.adapters.wiki.endpoints import WIKIDATA_HOST
from torrcast.adapters.wiki.wikidata_kin import WikidataKin
from torrcast.domain.facts.kin import Kin


def _reply(*rows: tuple[str, str, str]) -> dict[str, Any]:
    return {
        "results": {
            "bindings": [
                {
                    "item": {"value": f"http://www.wikidata.org/entity/{entity}"},
                    "itemLabel": {"value": label},
                    "date": {"value": date},
                }
                for entity, label, date in rows
            ]
        }
    }


def test_a_franchise_answers_with_its_other_pictures() -> None:
    """🔴 Живой замер 06-09-2026 (probe-franchise): 10 из 10 франшиз без чужих картин."""
    payload = _reply(("Q105993", "Крепкий орешек 2", "1990-07-04"))
    client = FakeJsonClient(lambda host, path, params: payload)

    assert WikidataKin(client).kin("Q105598", 1.0) == [Kin("Q105993", "Крепкий орешек 2", 1990)]
    host, _path, params = client.calls[0]
    assert host == WIKIDATA_HOST
    assert "wd:Q105598" in params["query"]


def test_a_stranger_string_never_reaches_the_body_of_the_query() -> None:
    """🔴 Идентификатор уезжает в ТЕЛО SPARQL: чужой знак в нём - это чужой запрос."""
    client = FakeJsonClient(lambda host, path, params: _reply())
    assert WikidataKin(client).kin("} } INSERT DATA { x", 1.0) == []
    assert client.calls == [], "мусор поехал в Wikidata запросом"


def test_a_refused_network_is_told_apart_from_a_franchise_without_kin() -> None:
    """🔴 Отказ сети поднимается наверх, а не приезжает пустой полкой.

    Пустой список отсюда кэшируется навсегда, и молчание сети в его виде гасило полку на
    всю жизнь установки (:meth:`torrcast.usecases.franchise_kin.FranchiseKin.of`).
    """

    def refuse(host: str, path: str, params: dict[str, str]) -> Any:
        raise OSError("HTTP 429")

    with pytest.raises(OSError, match="HTTP 429"):
        WikidataKin(FakeJsonClient(refuse)).kin("Q105598", 1.0)


def test_a_picture_without_a_franchise_answers_with_an_empty_shelf() -> None:
    """Пустой ответ SPARQL значит «родни нет», и полка честно скрывается."""
    client = FakeJsonClient(lambda host, path, params: _reply())
    assert WikidataKin(client).kin("Q1", 1.0) == []
