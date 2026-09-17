"""Зеркало :mod:`torrcast.domain.facts.read_kin`: родня картины из ответа SPARQL."""

from torrcast.domain.facts.kin import Kin
from torrcast.domain.facts.read_kin import read_kin
from torrcast.domain.json_value import JsonValue


def _reply(*rows: tuple[str, str, str]) -> JsonValue:
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


def _reply_with_ru(*rows: tuple[str, str, str, str]) -> JsonValue:
    return {
        "results": {
            "bindings": [
                {
                    "item": {"value": f"http://www.wikidata.org/entity/{entity}"},
                    "itemLabel": {"value": label},
                    "itemLabelRu": {"value": ru},
                    "date": {"value": date},
                }
                for entity, label, ru, date in rows
            ]
        }
    }


def test_kin_come_back_in_the_order_they_first_appeared() -> None:
    """Полка рода печатается в порядке ответа, а не пересортированной."""
    payload = _reply(
        ("Q105993", "Крепкий орешек 2", "1990-07-04"),
        ("Q72276", "Крепкий орешек: Хороший день, чтобы умереть", "2013-02-14"),
    )
    assert read_kin(payload) == [
        Kin("Q105993", "Крепкий орешек 2", 1990),
        Kin("Q72276", "Крепкий орешек: Хороший день, чтобы умереть", 2013),
    ]


def test_several_dates_of_one_picture_collapse_to_the_earliest_year() -> None:
    """Дат проката бывает несколько (разные страны) - берётся самая ранняя."""
    payload = _reply(
        ("Q46717", "Пираты Карибского моря", "2003-07-09"),
        ("Q46717", "Пираты Карибского моря", "2003-06-28"),
    )
    assert read_kin(payload) == [Kin("Q46717", "Пираты Карибского моря", 2003)]


def test_a_picture_without_any_date_still_carries_its_name() -> None:
    """Год не сверен - полка не молчит вовсе, показывает то, что известно."""
    payload = _reply(("Q121862910", "Джон Уик 5", ""))
    assert read_kin(payload) == [Kin("Q121862910", "Джон Уик 5", None)]


def test_a_pure_russian_label_lands_on_kin_ru_next_to_the_fallback_name() -> None:
    """TC-1321: ``itemLabelRu`` - живой русский ярлык, отдельно от запасного ``itemLabel``
    (который у «Saving Private Ryan» сползает на английский, хотя ``ru`` у Wikidata есть)."""
    row = ("Q165817", "Saving Private Ryan", "Спасти рядового Райана", "1998-07-24")
    assert read_kin(_reply_with_ru(row)) == [
        Kin("Q165817", "Saving Private Ryan", 1998, ru="Спасти рядового Райана")
    ]


def test_no_russian_wikidata_label_leaves_kin_ru_empty() -> None:
    """Нет ``itemLabelRu`` в ответе - поле пустое, а не выдуманное: последнее слово
    за отсевом кириллицей в :func:`web.related_lookup._spoken`."""
    payload = _reply(("Q9", "Black Panther III", ""))
    assert read_kin(payload) == [Kin("Q9", "Black Panther III", None, ru="")]


def test_an_answer_without_rows_is_an_empty_shelf_and_not_an_error() -> None:
    """Пустой ответ значит «родни нет», и это законный исход, а не сбой."""
    assert read_kin(_reply()) == []
    assert read_kin(None) == []
    assert read_kin({"results": {"bindings": [{"item": {"value": "мусор"}}]}}) == []
