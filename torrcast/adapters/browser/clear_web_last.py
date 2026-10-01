"""Стирает отметку последней серии (:mod:`torrcast.adapters.browser.write_web_last`).

Зовёт его :meth:`torrcast.adapters.browser.browser_receiver.BrowserReceiver.play`: новый
показ получает свежий ключ, и отметка прошлого ему не наследство - ящик вкладки
(:mod:`web.box`) иначе отдавал бы чужой ``last`` каждому следующему показу.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from torrcast.adapters.browser.web_last_path import web_last_path


def clear_web_last(out: Path) -> None:
    """Стереть отметку; её и не было - не беда."""
    with contextlib.suppress(OSError):
        web_last_path(out).unlink(missing_ok=True)
