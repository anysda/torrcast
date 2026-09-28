"""Английский словарь надписей страницы: ``GET /api/phrases``."""

from __future__ import annotations

import json

from torrcast.domain.catalogs.web.en import en as english
from web.answer import Answer
from web.request import Request


def phrases(request: Request) -> Answer:
    """Отдать единый английский словарь, независимо от доводов запроса."""
    del request
    return Answer(200, json.dumps(english(), ensure_ascii=False).encode("utf-8"))
