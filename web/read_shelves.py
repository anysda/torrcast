"""Тело полок с диска: переживает рестарт, а битый или пропавший файл показ не роняет."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from torrcast.domain.json_value import JsonValue
from web.built_by_rule import FIELD, RULE


def read_shelves(path: Path) -> dict[str, JsonValue]:
    """Сохранённое тело; нет его или оно битое - пустые полки, а не выдуманная картина."""
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = None
    # Клеймо велит пересобрать, но прежнее или бесклейменное тело остаётся экраном.
    if isinstance(raw, dict):
        return raw
    return {FIELD: RULE, "fresh": [], "popular": [], "built_at": None}


__all__ = ["read_shelves"]
