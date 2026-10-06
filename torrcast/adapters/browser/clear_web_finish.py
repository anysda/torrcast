"""Стирает одноразовую команду вкладке."""

from __future__ import annotations

import contextlib
from pathlib import Path

from torrcast.adapters.browser.web_finish_path import web_finish_path


def clear_web_finish(out: Path) -> None:
    """Команды нет или уже забрана - это штатно."""
    with contextlib.suppress(OSError):
        web_finish_path(out).unlink(missing_ok=True)
