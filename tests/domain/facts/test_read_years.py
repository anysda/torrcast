"""Зеркало :mod:`torrcast.domain.facts.read_years`: годы выхода из ответа SPARQL."""

from torrcast.domain.facts.read_years import read_years
from torrcast.domain.json_value import JsonValue


def _reply(*rows: tuple[str, str]) -> JsonValue:
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


def test_all_the_years_of_one_picture_are_kept_and_not_the_first_one() -> None:
    """🔴 Годов у картины бывает несколько: фестиваль, прокат, издания - это она же.

    Возьми отсюда самый ранний, и картина, которую раздача подписала годом проката,
    осталась бы без постера при живой и правильной статье.
    """
    payload = _reply(("Q61448040", "2019-05-21T00:00:00Z"), ("Q61448040", "2020-01-01"))
    assert read_years(payload) == {"Q61448040": {2019, 2020}}


def test_several_pictures_come_back_from_one_request() -> None:
    """Ради этого запрос и собирается пачкой: весь список одним походом."""
    payload = _reply(("Q83495", "1999-03-31"), ("Q192724", "2003-05-15"))
    assert read_years(payload) == {"Q83495": {1999}, "Q192724": {2003}}


def test_an_answer_without_rows_is_an_empty_map_and_not_an_error() -> None:
    """Пустой ответ значит «не сказано», и зовущий решает это сам."""
    assert read_years(_reply()) == {}
    assert read_years(None) == {}
    assert read_years({"results": {"bindings": [{"item": {"value": "мусор"}}]}}) == {}
