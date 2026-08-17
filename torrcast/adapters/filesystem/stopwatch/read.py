"""Чтение ленты меток по возрастанию времени: обе ноги старта в одном порядке.

Читает её таблица секундомера и щупы замера старта."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any


def read(path: str | Path) -> list[dict[str, Any]]:
    """Лента меток по возрастанию времени."""
    found: list[dict[str, Any]] = []
    with contextlib.suppress(OSError):
        for raw in Path(path).read_text("utf-8").splitlines():
            with contextlib.suppress(ValueError):
                found.append(json.loads(raw))
    return sorted(found, key=lambda entry: float(entry.get("at", 0.0)))
