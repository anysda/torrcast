"""Быстрый кусок карточки плитки, пока круг раздач ещё считается."""

from __future__ import annotations

import json
from collections.abc import Callable

from torrcast.domain.json_value import JsonValue
from torrcast.domain.spoken_title import spoken_title
from torrcast.runtime.menu_facts import MenuFacts
from web.answer import Answer
from web.rating_score import rating_score
from web.request import Request
from web.warm_cache import WarmCache

Related = Callable[[str, bool], list[JsonValue] | None]
_PARTIAL = "X-Torrcast-Partial"


def preview(
    request: Request, key: str, warm: WarmCache, related_of: Related
) -> Answer | None:
    """Ответить сведениями плитки, не ожидая поиска раздач."""
    if warm.ready(request.query.get("query", "")) is not None or request.query.get("wait") == "1":
        return None
    title = request.query.get("title", "").strip()
    kind = request.query.get("kind", "")
    year = _year(request.query.get("year", ""))
    if not title or kind not in {"movie", "tv"} or year is None:
        return None
    warm.ask([request.query["query"]])
    facts = MenuFacts([(title, year, kind)], budget=0.0)
    facts.start()
    fact = facts.ready(title, year)
    told = facts.answered(title, year)
    related = related_of(title, kind == "tv")
    body: dict[str, JsonValue] = {
        "pick": 0,
        "title": title,
        "shown": request.query.get("shown", "") or spoken_title(title, ""),
        "original": None,
        "year": year,
        "kind": kind,
        "runtime": 0.0,
        "runtime_estimated": False,
        "rating": rating_score(fact.rating),
        "blurb": fact.about if told else None,
        "poster": None,
        "voices": [],
        "resumable": False,
        "label": "",
        "playing": False,
        "seasons": [],
        "related": _others(key, related),
        "releases_count": 0,
        "sources_count": 0,
        "searching": True,
    }
    return Answer(200, json.dumps(body, ensure_ascii=False).encode("utf-8"), extra=((_PARTIAL, "1"),))


def _year(value: str) -> int | None:
    """Год из строки маршрута, только правдоподобное целое."""
    try:
        year = int(value)
    except ValueError:
        return None
    return year if 1800 <= year <= 3000 else None


def _others(key: str, related: list[JsonValue] | None) -> list[JsonValue] | None:
    """Не ставить открытую плитку в её же полку франшизы."""
    if related is None:
        return None
    return [tile for tile in related if not isinstance(tile, dict) or tile.get("key") != key]


__all__ = ["preview"]
