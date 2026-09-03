"""Ответ SPARQL на годы выхода пачки картин; зовёт адаптер Wikidata."""

from __future__ import annotations

import re
from typing import Final

from torrcast.domain.json_map import json_map
from torrcast.domain.json_rows import json_rows
from torrcast.domain.json_value import JsonValue

#: Хвост адреса сущности Wikidata: сам идентификатор приезжает полным URI
#: («http://www.wikidata.org/entity/Q83495»), а ключом тут служит его конец.
_ENTITY_RE: Final = re.compile(r"(Q\d+)$")
#: Начало даты ISO: у старого кино точность бывает до года («1960-01-01T00:00:00Z»).
_DATE_RE: Final = re.compile(r"(\d{4})-")


def read_years(payload: JsonValue) -> dict[str, set[int]]:
    """Ответ SPARQL → годы выхода по идентификатору картины; пусто - пустая карта.

    Годов у одной картины бывает несколько (разные страны проката, издания), и берутся
    ВСЕ: сверка идёт на совпадение с любым из них, а не с самым ранним. Премьера на
    фестивале годом раньше проката - это та же картина, а не соседка по имени.
    """
    if not isinstance(payload, dict):
        return {}
    out: dict[str, set[int]] = {}
    for row in json_rows(json_map(payload.get("results")).get("bindings")):
        cell = json_map(row)
        entity = _ENTITY_RE.search(str(json_map(cell.get("item")).get("value", "")))
        date = _DATE_RE.match(str(json_map(cell.get("date")).get("value", "")))
        if entity and date:
            out.setdefault(entity.group(1), set()).add(int(date.group(1)))
    return out
