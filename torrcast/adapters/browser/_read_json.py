"""Читает JSON, записанный :func:`torrcast.adapters.browser._write_json._write_json`."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any] | None:
    """Разобранный объект файла, а файла нет или он битый - ``None``."""
    with contextlib.suppress(OSError, ValueError):
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    return None
