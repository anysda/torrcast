"""Проверяет разбор ответа SPARQL на идентификатор IMDb и хронометраж."""

from typing import Any

from torrcast.domain.facts.read_sparql import read_sparql


def test_sparql_gives_the_imdb_id_and_the_running_time() -> None:
    """Живой ответ Wikidata: у «Тачек» есть и то и другое, у страницы значений — ничего."""
    payload: dict[str, Any] = {
        "results": {
            "bindings": [
                {
                    "item": {"value": "http://www.wikidata.org/entity/Q182153"},
                    "imdb": {"value": "tt0317219"},
                    "dur": {"value": "116"},
                },
                {"item": {"value": "http://www.wikidata.org/entity/Q1183953"}},
            ]
        }
    }
    assert read_sparql(payload) == {"Q182153": ("tt0317219", 116), "Q1183953": ("", 0)}


def test_an_answer_that_is_not_a_dictionary_is_no_answer() -> None:
    """Ответ не того вида - пустой словарь, а не исключение в путь до меню."""
    assert read_sparql("не словарь") == {}
