"""Что человек видит прямо сейчас: ``POST /api/seen``.

Страница называет запросы плиток, попавших ей на экран (``web/static/warm.js``), и
прогрев греет ровно их (:class:`web.warm_cache.WarmCache`). Ответ не ждёт ни сети, ни
очереди: он говорит только, сколько запросов от этого экрана пойдут в сеть, - и говорит
это странице, а не человеку, поэтому строк каталога тут нет.

Пустой экран - законное тело: так страница говорит «плиток не видно» (человек ушёл в
поиск, и результатов ещё нет), и очередь прошлого экрана снимается, не мешая живому.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from torrcast.domain.json_value import JsonValue
from web.answer import Answer
from web.refusal import refusal
from web.request import Request
from web.warm_targets import WarmTarget
from web.warm_wiring import TARGETS


def seen(request: Request) -> Answer:
    """Принять экран плиток и вернуть число кругов, поставленных в очередь."""
    raw = request.body.get("tiles")
    if not isinstance(raw, list):
        return refusal(400, "bad_tiles")
    queued = TARGETS.observe(_targets(raw))
    return Answer(200, json.dumps({"queued": queued}).encode("utf-8"))


def _targets(rows: Sequence[JsonValue]) -> list[WarmTarget]:
    """Оставить только плитки, для которых адрес дал достаточно фактов."""
    targets: list[WarmTarget] = []
    for row in rows:
        if isinstance(row, str):
            targets.append((row, "", "", None, ""))
            continue
        if not isinstance(row, dict):
            continue
        query, key, title = row.get("query"), row.get("key"), row.get("title")
        year, kind = row.get("year"), row.get("kind")
        if not isinstance(query, str):
            continue
        if not isinstance(key, str) or not isinstance(title, str):
            targets.append((query, "", "", None, ""))
        elif isinstance(year, int) and isinstance(kind, str) and kind in {"movie", "tv"}:
            targets.append((query, key, title, year, kind))
        else:
            targets.append((query, "", "", None, ""))
    return targets
