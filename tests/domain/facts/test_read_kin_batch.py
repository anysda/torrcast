"""Зеркало :mod:`torrcast.domain.facts.read_kin_batch`: родня пачки картин по ``?src``."""

import pytest

from torrcast.domain.facts.kin import Kin
from torrcast.domain.facts.read_kin_batch import read_kin_batch
from torrcast.domain.json_value import JsonValue


def _reply(*rows: tuple[str, str, str, str]) -> JsonValue:
    entity = "http://www.wikidata.org/entity/"
    return {
        "results": {
            "bindings": [
                {
                    "src": {"value": entity + source},
                    "item": {"value": entity + item},
                    "itemLabel": {"value": label},
                    "date": {"value": date},
                }
                for source, item, label, date in rows
            ]
        }
    }


def test_a_batch_answer_is_split_by_the_asked_picture() -> None:
    """Строки пачки делятся по ``?src``; картина без строк - пустая полка, чужой ``?src`` мимо."""
    payload = _reply(
        ("Q105598", "Q105993", "Крепкий орешек 2", "1990-07-04"),
        ("Q105598", "Q72276", "Крепкий орешек: Хороший день, чтобы умереть", "2013-02-14"),
        ("Q404", "Q9", "Чужая", "2000-01-01"),
    )

    assert read_kin_batch(payload, ["Q105598", "Q1"]) == {
        "Q105598": [
            Kin("Q105993", "Крепкий орешек 2", 1990),
            Kin("Q72276", "Крепкий орешек: Хороший день, чтобы умереть", 2013),
        ],
        "Q1": [],
    }


def test_a_batch_answer_without_rows_is_a_failure_not_empty_shelves() -> None:
    """🔴 Пустая родня кэшируется навсегда: ответ без ``bindings`` обязан подняться сбоем."""
    with pytest.raises(ValueError):
        read_kin_batch({"error": "rate limited"}, ["Q105598"])
