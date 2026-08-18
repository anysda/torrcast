"""Статья по имени и склейка нескольких ответов Википедии; зовут адаптеры справки.

Сам ответ на статьи и обратный путь имён разбирает сосед
(:func:`~torrcast.domain.facts.wiki_pages.wiki_pages`).
"""

from __future__ import annotations

from collections.abc import Sequence

from torrcast.domain.facts.wiki_pages import HOPS
from torrcast.domain.json_map import json_map
from torrcast.domain.json_rows import json_rows
from torrcast.domain.json_value import JsonValue


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
    пути имени - нормализация регистра и перенаправления
    (:func:`~torrcast.domain.facts.wiki_pages.wiki_pages`).
    """
    query: dict[str, JsonValue] = {}
    for kind in ("pages", *HOPS):
        rows: list[JsonValue] = []
        for payload in answers:
            rows.extend(json_rows(json_map(json_map(payload).get("query")).get(kind)))
        query[kind] = rows
    return {"query": query}
