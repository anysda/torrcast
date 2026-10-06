"""Кладёт одноразовую команду вкладке завершить серию штатным концом."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.browser.web_finish_path import web_finish_path
from torrcast.adapters.browser.write_json import write_json


def write_web_finish(out: Path, key: str, at: float) -> None:
    """Назначить сеансу ``key`` целевую секунду; чужая вкладка её не возьмёт."""
    write_json(web_finish_path(out), {"key": key, "at": at})
