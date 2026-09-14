"""Запуск полки открытой карточки без повторного паспорта."""

from __future__ import annotations

from typing import Any

from web.kin_ahead import KIN_AHEAD
from web.request import Request


def start_related(request: Request, facts: Any, related: Any) -> tuple[str, int, str] | None:
    """Начать полку открытой плитки до любого лимита фонового прогрева.

    ``seen`` вправе греть только одну плитку экрана: иначе восемь паспортов забивают
    Wikipedia и лишают человека описания. Открытая карточка не является фоновым экраном,
    поэтому её родня заводится сама, даже если она не была первой видимой плиткой или
    ``seen`` уже заменил свою очередь.
    """
    title = request.query.get("title", "").strip()
    kind = request.query.get("kind", "")
    try:
        year = int(request.query.get("year", ""))
    except ValueError:
        return None
    if title and kind in {"movie", "tv"} and 1800 <= year <= 3000:
        fact = facts.of(title, year, kind).ready(title, year)
        known = "" if kind == "tv" else KIN_AHEAD.entity(title, year)
        if entity := str(getattr(fact, "entity", "")) or known:
            related.retry(title, kind == "tv", entity)
        return title, year, kind
    return None
