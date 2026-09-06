"""Ответ SPARQL на родню картины из франшизы; зовёт адаптер Wikidata."""

from __future__ import annotations

import re
from typing import Final

from torrcast.domain.facts.kin import Kin
from torrcast.domain.json_map import json_map
from torrcast.domain.json_rows import json_rows
from torrcast.domain.json_value import JsonValue

#: Начало даты ISO: у старого кино точность бывает до года («1960-01-01T00:00:00Z»).
_DATE_RE: Final = re.compile(r"(\d{4})-")


def read_kin(payload: JsonValue) -> list[Kin]:
    """Ответ SPARQL → список родни в порядке первого появления; пусто - родни нет.

    Одна картина отвечает НЕСКОЛЬКИМИ рядами, если у неё несколько дат публикации
    (прокат разных стран) - берётся самая ранняя, тем же правилом, что и у постера
    (:func:`~torrcast.domain.facts.read_years.read_years`). Имя картины от ряда к ряду не
    меняется - разводит их только дата.
    """
    if not isinstance(payload, dict):
        return []
    names: dict[str, str] = {}
    years: dict[str, set[int]] = {}
    order: list[str] = []
    for row in json_rows(json_map(payload.get("results")).get("bindings")):
        cell = json_map(row)
        item = str(json_map(cell.get("item")).get("value", "")).rsplit("/", 1)[-1]
        if not item.startswith("Q"):
            continue
        if item not in names:
            order.append(item)
            names[item] = ""
        label = str(json_map(cell.get("itemLabel")).get("value", ""))
        if label:
            names[item] = label
        date = _DATE_RE.match(str(json_map(cell.get("date")).get("value", "")))
        if date:
            years.setdefault(item, set()).add(int(date.group(1)))
    return [Kin(item, names[item], min(years[item]) if item in years else None) for item in order]
