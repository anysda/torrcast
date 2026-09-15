"""Страница называет записи, которые у неё на экране: ``POST /api/hold``.

Главная шлёт ключи плиток «Продолжить», карточка - свой; держатель
(:class:`web.record_hold.RecordHold`) не даёт TorrServer закрыть их раздачи, пока зов идёт.
Ключ без записи в истории молча пропускается: держать нечего.
"""

from __future__ import annotations

import json

from torrcast.adapters.filesystem.state.load_config import load_config
from web.answer import Answer
from web.record_hold import RECORD_HOLD
from web.refusal import refusal
from web.request import Request

#: Длиннее ключ картины не бывает: тот же потолок, что у ``POST /api/card-left``.
_KEY_LIMIT = 300


def hold(request: Request) -> Answer:
    """Продлить аренду записанных раздач названных ключей."""
    raw = request.body.get("keys")
    if not isinstance(raw, list):
        return refusal(400, "bad_keys")
    keys = [key for key in raw if isinstance(key, str) and 0 < len(key) <= _KEY_LIMIT]
    started = RECORD_HOLD.touch(load_config().torrserver_url, keys)
    return Answer(200, json.dumps({"started": started}).encode("utf-8"))
