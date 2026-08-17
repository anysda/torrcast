"""Ответ SPARQL на P577 в самый ранний год; зовёт адаптер Wikidata."""

from __future__ import annotations

import re
from typing import Any


def read_published(payload: Any) -> int | None:
    """Ответ SPARQL на P577 → самый ранний год; ни одной даты - ``None``.

    Дата приезжает ISO-строкой («2016-11-14T00:00:00Z», у старого кино с точностью до года
    - «1960-01-01T00:00:00Z»); год - её первые четыре цифры.
    """
    if not isinstance(payload, dict):
        return None
    rows = (payload.get("results", {}) or {}).get("bindings", [])
    years: list[int] = []
    for row in rows:
        value = row.get("date", {}).get("value", "")
        match = re.match(r"(\d{4})-", value)
        if match:
            years.append(int(match.group(1)))
    return min(years) if years else None
