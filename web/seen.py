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

from web.answer import Answer
from web.refusal import refusal
from web.request import Request
from web.warm_wiring import WARM


def seen(request: Request) -> Answer:
    """Принять экран запросов и вернуть число тех, что прогрев возьмёт в работу."""
    raw = request.body.get("tiles")
    if not isinstance(raw, list):
        return refusal(400, "bad_tiles")
    queued = WARM.ask([row for row in raw if isinstance(row, str)])
    return Answer(200, json.dumps({"queued": queued}).encode("utf-8"))
