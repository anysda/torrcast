"""Ответ SPARQL на P577 в самый ранний год; зовёт адаптер Wikidata."""

from __future__ import annotations

import re

from torrcast.domain.json_map import json_map
from torrcast.domain.json_rows import json_rows
from torrcast.domain.json_value import JsonValue


def read_published(payload: JsonValue) -> int | None:
    """Ответ SPARQL на P577 → самый ранний год; ни одной даты - ``None``.

    Дата приезжает ISO-строкой («2016-11-14T00:00:00Z», у старого кино с точностью до года
    - «1960-01-01T00:00:00Z»); год - её первые четыре цифры.
    """
    if not isinstance(payload, dict):
        return None
    rows = json_rows(json_map(payload.get("results")).get("bindings"))
    years: list[int] = []
    for row in rows:
        value = str(json_map(json_map(row).get("date")).get("value", ""))
        match = re.match(r"(\d{4})-", value)
        if match:
            years.append(int(match.group(1)))
    return min(years) if years else None
