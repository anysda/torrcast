"""Имя значения JSON: разобранный ответ службы под него подходит целиком."""

import json

from torrcast.ports.json_value import JsonValue


def test_a_parsed_answer_of_a_service_is_a_json_value() -> None:
    """Дерево из скаляров, списков и словарей - это и есть весь договор."""
    parsed: JsonValue = json.loads('{"a": [1, 2.5, "три", true, null], "b": {"c": 0}}')

    assert isinstance(parsed, dict)
    assert parsed["b"] == {"c": 0}
