"""Читает команду вкладке довести текущую серию до конца."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from torrcast.adapters.browser.read_json import read_json
from torrcast.adapters.browser.web_finish_path import web_finish_path


def read_web_finish(out: Path) -> dict[str, Any]:
    """Команда или пустой словарь, если вкладке доводить нечего."""
    return read_json(web_finish_path(out)) or {}
