"""Путь одноразовой команды вкладке довести текущую серию до конца."""

from __future__ import annotations

from pathlib import Path
from typing import Final

WEB_FINISH_FILE: Final = "web_finish.json"


def web_finish_path(out: Path) -> Path:
    """Файл команды рядом с ящиком и позицией вкладки."""
    return out / WEB_FINISH_FILE
