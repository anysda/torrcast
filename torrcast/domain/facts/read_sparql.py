"""Ответ SPARQL в пары «IMDb, минуты»; зовёт адаптер Wikidata."""

from __future__ import annotations

import re

from torrcast.domain.json_map import json_map
from torrcast.domain.json_rows import json_rows
from torrcast.domain.json_value import JsonValue


def read_sparql(payload: JsonValue) -> dict[str, tuple[str, int]]:
    """Ответ SPARQL → ``{Q-идентификатор: (tt…, минуты)}``; чего нет — того нет."""
    out: dict[str, tuple[str, int]] = {}
    if not isinstance(payload, dict):
        return {}
    rows = json_rows(json_map(payload.get("results")).get("bindings"))
    for row in rows:
        cells = json_map(row)
        item = str(json_map(cells.get("item")).get("value", "")).rsplit("/", 1)[-1]
        if not item.startswith("Q"):
            continue
        imdb = str(json_map(cells.get("imdb")).get("value", ""))
        raw = str(json_map(cells.get("dur")).get("value", ""))
        minutes = int(float(raw)) if re.fullmatch(r"\d+(\.\d+)?", raw) else 0
        out[item] = (imdb, minutes)
    return out
