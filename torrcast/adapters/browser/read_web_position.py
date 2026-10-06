"""Читает последнюю позицию, присланную вкладкой; зовёт её приёмник-браузер.

Зовёт его :meth:`torrcast.adapters.browser.browser_receiver.BrowserReceiver.position`,
и только он: у мостовой стороны (:mod:`web.position`) читать тут нечего - она только пишет.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from torrcast.adapters.browser.read_json import read_json
from torrcast.adapters.browser.web_position_path import web_position_path


def read_web_position(out: Path) -> dict[str, Any] | None:
    """Последняя позиция вкладки, а записи нет или она битая - ``None``."""
    return read_json(web_position_path(out))
