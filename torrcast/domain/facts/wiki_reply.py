"""Разбор ответа Википедии на статьи и обратный путь имён; зовут адаптеры справки."""

from __future__ import annotations

from collections.abc import Sequence

from torrcast.domain.facts.settings import _SEARCH_HITS
from torrcast.domain.json_map import json_map
from torrcast.domain.json_number import json_number
from torrcast.domain.json_rows import json_rows
from torrcast.domain.json_value import JsonValue

#: Списки обратного пути имени, которыми отвечает API: нормализация регистра и
#: перенаправления. Оба читаются одинаково, поэтому и названы одним перечнем.
_HOPS = ("normalized", "redirects")


def _pages(payload: JsonValue) -> tuple[dict[str, str], dict[str, JsonValue]]:
    """Ответ Википедии → (обратный путь имён, статьи по заголовку)."""
    query = json_map(json_map(payload).get("query"))
    hops: dict[str, str] = {}
    for kind in _HOPS:
        for hop in json_rows(query.get(kind)):
            hops[str(json_map(hop).get("from", ""))] = str(json_map(hop).get("to", ""))
    return hops, {
        str(json_map(page).get("title", "")): page for page in json_rows(query.get("pages"))
    }


def _article(
    name: str, hops: dict[str, str], pages: dict[str, JsonValue]
) -> dict[str, JsonValue] | None:
    """Статья по запрошенному имени; страница значений и пустышка статьёй не считаются."""
    seen = name
    for _ in range(3):  # нормализация, затем перенаправление; больше не бывает
        seen = hops.get(seen, seen)
    page = json_map(pages.get(seen))
    if not page or page.get("missing") or "disambiguation" in json_map(page.get("pageprops")):
        return None
    return page


def _merged(answers: Sequence[JsonValue]) -> dict[str, JsonValue]:
    """Несколько ответов Википедии - в один: разбор кандидатов о пакетах знать не должен.

    Склеиваются ровно те три списка, которыми отвечает API: сами статьи и оба обратных
    пути имени - нормализация регистра и перенаправления (:func:`_pages`).
    """
    query: dict[str, JsonValue] = {}
    for kind in ("pages", *_HOPS):
        rows: list[JsonValue] = []
        for payload in answers:
            rows.extend(json_rows(json_map(json_map(payload).get("query")).get(kind)))
        query[kind] = rows
    return {"query": query}


def _ranked(payload: JsonValue) -> list[JsonValue]:
    """Найденные статьи в порядке выдачи поиска; страницы значений сюда не попадают."""
    _hops, pages = _pages(payload)
    out = [
        page
        for page in pages.values()
        if "disambiguation" not in json_map(json_map(page).get("pageprops"))
    ]
    return sorted(
        out, key=lambda page: int(json_number(json_map(page).get("index") or _SEARCH_HITS))
    )
