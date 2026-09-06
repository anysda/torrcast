"""Отказ страницы одним словом: тело у него такое же, как у моста."""

from __future__ import annotations

import json

from web.answer import Answer


def refusal(code: int, word: str) -> Answer:
    """Собрать отказ ``{"error": слово}``: страница отвечает мосту в один голос."""
    return Answer(code, json.dumps({"error": word}).encode("utf-8"))
