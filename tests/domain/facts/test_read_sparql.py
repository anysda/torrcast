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


def test_a_duration_in_seconds_is_not_taken_for_minutes() -> None:
    """Живой ответ про «Оппенгеймера»: 10809 - это секунды, то есть ровно три часа."""
    payload: dict[str, Any] = {
        "results": {
            "bindings": [
                {
                    "item": {"value": "http://www.wikidata.org/entity/Q101890270"},
                    "imdb": {"value": "tt15398776"},
                    "dur": {"value": "10809"},
                    "unit": {"value": "http://www.wikidata.org/entity/Q11574"},
                }
            ]
        }
    }
    assert read_sparql(payload) == {"Q101890270": ("tt15398776", 180)}


def test_hours_become_minutes_too() -> None:
    """Единица бывает и крупнее минуты - число всё равно приводится к минутам."""
    payload: dict[str, Any] = {
        "results": {
            "bindings": [
                {
                    "item": {"value": "http://www.wikidata.org/entity/Q1"},
                    "dur": {"value": "1.5"},
                    "unit": {"value": "http://www.wikidata.org/entity/Q25235"},
                }
            ]
        }
    }
    assert read_sparql(payload) == {"Q1": ("", 90)}


def test_an_answer_without_a_unit_keeps_reading_the_number_as_minutes() -> None:
    """Так записано у большинства картин, и незнакомая единица ничего не должна ломать."""

    def one(unit: dict[str, str] | None) -> dict[str, Any]:
        row: dict[str, Any] = {
            "item": {"value": "http://www.wikidata.org/entity/Q182153"},
            "dur": {"value": "116"},
        }
        if unit is not None:
            row["unit"] = unit
        return {"results": {"bindings": [row]}}

    assert read_sparql(one(None)) == {"Q182153": ("", 116)}
    assert read_sparql(one({"value": "http://www.wikidata.org/entity/Q42"})) == {
        "Q182153": ("", 116)
    }
