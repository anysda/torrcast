"""Ответ Википедии в статьи и обратный путь имён; зовут адаптеры и разбор справки."""

from __future__ import annotations

from torrcast.domain.json_map import json_map
from torrcast.domain.json_rows import json_rows
from torrcast.domain.json_value import JsonValue

#: Списки обратного пути имени, которыми отвечает API: нормализация регистра и
#: перенаправления. Оба читаются одинаково, поэтому и названы одним перечнем.
HOPS = ("normalized", "redirects")


def wiki_pages(payload: JsonValue) -> tuple[dict[str, str], dict[str, JsonValue]]:
    """Ответ Википедии → (обратный путь имён, статьи по заголовку)."""
    query = json_map(json_map(payload).get("query"))
    hops: dict[str, str] = {}
    for kind in HOPS:
        for hop in json_rows(query.get(kind)):
            hops[str(json_map(hop).get("from", ""))] = str(json_map(hop).get("to", ""))
    return hops, {
        str(json_map(page).get("title", "")): page for page in json_rows(query.get("pages"))
    }
