"""Читает ключ показа, отмеченного последним (:mod:`torrcast.adapters.browser.write_web_last`).

Зовут его приёмник-браузер на конце серии
(:meth:`torrcast.adapters.browser.browser_receiver.BrowserReceiver.position`) и ящик
вкладки (:mod:`web.box`): перезагруженная или вторая вкладка узнаёт об «Отмене» оттуда.
"""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.browser.read_json import read_json
from torrcast.adapters.browser.web_last_path import web_last_path


def read_web_last(out: Path) -> str:
    """Ключ отмеченного показа, а отметки нет или она битая - пустая строка."""
    record = read_json(web_last_path(out))
    return str(record.get("key", "")) if record is not None else ""
