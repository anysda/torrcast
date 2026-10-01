"""Отмечает показ ``key`` последним: после него следующую серию не заводить.

Зовёт её ``POST /api/web/position`` с ``last: true`` (:mod:`web.position`), когда
зритель нажал «Отмена» на плашке следующей серии во вкладке.
"""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.browser._write_json import _write_json
from torrcast.adapters.browser.web_last_path import web_last_path


def write_web_last(out: Path, key: str) -> None:
    """Записать ключ показа, после которого следующей серии не будет."""
    _write_json(web_last_path(out), {"key": key})
