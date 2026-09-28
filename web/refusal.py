"""Отказ страницы одним словом: тело у него такое же, как у моста."""

from __future__ import annotations

import json
from collections.abc import Mapping

from web.answer import Answer


def refusal(code: int, word: str, reason: Mapping[str, object] | None = None) -> Answer:
    """Собрать отказ; named reasons carry a page key and its values."""
    body: dict[str, object] = {"error": word}
    if reason is not None:
        body["reason"] = reason
    return Answer(code, json.dumps(body).encode("utf-8"))
