"""Убирает задание вкладке: показ кончился, смотреть страницу больше нечему.

Зовёт его :meth:`torrcast.adapters.browser.browser_receiver.BrowserReceiver.stop`
и он же перед новым :meth:`~torrcast.adapters.browser.browser_receiver.BrowserReceiver.play`
- чужое задание прошлого сеанса не годится в наследство новому.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from torrcast.adapters.browser.web_box_path import web_box_path


def clear_web_box(out: Path) -> None:
    """Убрать задание; файла и не было - не беда."""
    with contextlib.suppress(OSError):
        web_box_path(out).unlink(missing_ok=True)
