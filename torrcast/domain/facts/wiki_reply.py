"""Разбор ответа Википедии на статьи и обратный путь имён; зовут адаптеры справки."""

from __future__ import annotations

from typing import Any

from torrcast.domain.facts.settings import _SEARCH_HITS


def _pages(payload: Any) -> tuple[dict[str, str], dict[str, Any]]:
    """Ответ Википедии → (обратный путь имён, статьи по заголовку)."""
    query = payload.get("query", {}) if isinstance(payload, dict) else {}
    hops: dict[str, str] = {}
    for kind in ("normalized", "redirects"):
        for hop in query.get(kind, []) or []:
            hops[hop.get("from", "")] = hop.get("to", "")
    return hops, {page.get("title", ""): page for page in query.get("pages", []) or []}


def _article(name: str, hops: dict[str, str], pages: dict[str, Any]) -> Any:
    """Статья по запрошенному имени; страница значений и пустышка статьёй не считаются."""
    seen = name
    for _ in range(3):  # нормализация, затем перенаправление; больше не бывает
        seen = hops.get(seen, seen)
    page = pages.get(seen)
    if not page or page.get("missing") or "disambiguation" in (page.get("pageprops") or {}):
        return None
    return page


def _merged(answers: list[Any]) -> dict[str, Any]:
    """Несколько ответов Википедии - в один: разбор кандидатов о пакетах знать не должен.

    Склеиваются ровно те три списка, которыми отвечает API: сами статьи и оба обратных
    пути имени - нормализация регистра и перенаправления (:func:`_pages`).
    """
    query: dict[str, list[Any]] = {"pages": [], "normalized": [], "redirects": []}
    for payload in answers:
        part = payload.get("query", {}) if isinstance(payload, dict) else {}
        for kind, rows in query.items():
            rows.extend(part.get(kind) or [])
    return {"query": query}


def _ranked(payload: Any) -> list[Any]:
    """Найденные статьи в порядке выдачи поиска; страницы значений сюда не попадают."""
    _hops, pages = _pages(payload)
    out = [page for page in pages.values() if "disambiguation" not in (page.get("pageprops") or {})]
    return sorted(out, key=lambda page: int(page.get("index") or _SEARCH_HITS))
