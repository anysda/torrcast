"""Найденные поиском Википедии статьи в порядке выдачи; зовут адаптеры справки."""

from __future__ import annotations

from torrcast.domain.facts.settings import _SEARCH_HITS
from torrcast.domain.facts.wiki_pages import wiki_pages
from torrcast.domain.json_map import json_map
from torrcast.domain.json_number import json_number
from torrcast.domain.json_value import JsonValue


def wiki_ranked(payload: JsonValue) -> list[JsonValue]:
    """Найденные статьи в порядке выдачи поиска; страницы значений сюда не попадают."""
    _hops, found = wiki_pages(payload)
    out = [
        page
        for page in found.values()
        if "disambiguation" not in json_map(json_map(page).get("pageprops"))
    ]
    return sorted(
        out, key=lambda page: int(json_number(json_map(page).get("index") or _SEARCH_HITS))
    )
