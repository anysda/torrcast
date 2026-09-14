"""Ответ SPARQL на родню пачки картин, разложенный по спрошенной; зовёт адаптер Wikidata."""

from __future__ import annotations

from torrcast.domain.facts.kin import Kin
from torrcast.domain.facts.read_kin import read_kin
from torrcast.domain.json_map import json_map
from torrcast.domain.json_rows import json_rows
from torrcast.domain.json_value import JsonValue


def read_kin_batch(payload: JsonValue, entities: list[str]) -> dict[str, list[Kin]]:
    """Ответ пачки → родня каждой спрошенной картины; строк у картины нет - родни нет.

    Строки делятся по ``?src`` и читаются тем же :func:`read_kin`, что и одиночный ответ.
    Порядок внутри картины - порядок её строк в пачке.
    """
    rows: dict[str, list[JsonValue]] = {entity: [] for entity in entities}
    bindings = json_map(payload).get("results")
    if not isinstance(json_map(bindings).get("bindings"), list):
        # Пустая родня ложится в кэш навсегда: ответ без рядов - не ответ, а сбой.
        raise ValueError("SPARQL batch answered without result rows")
    for row in json_rows(json_map(bindings).get("bindings")):
        source = str(json_map(json_map(row).get("src")).get("value", "")).rsplit("/", 1)[-1]
        if source in rows:
            rows[source].append(row)
    return {entity: read_kin({"results": {"bindings": found}}) for entity, found in rows.items()}
