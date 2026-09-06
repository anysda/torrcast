"""Кладёт задание вкладке: что играть, с какого места и каким ключом подписывать позицию.

Зовёт его :class:`torrcast.adapters.browser.browser_receiver.BrowserReceiver` из
:meth:`~torrcast.adapters.browser.browser_receiver.BrowserReceiver.play`, и только он.
"""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.browser._write_json import _write_json
from torrcast.adapters.browser.web_box_path import web_box_path


def write_web_box(out: Path, url: str, title: str, at: float, key: str) -> None:
    """Записать задание: ``url``, ``title``, место старта ``at`` и ключ сеанса ``key``.

    Ключ вкладка обязана вернуть с каждой позицией
    (:mod:`torrcast.adapters.browser.write_web_position`): им отличают текущий сеанс от
    чужой вкладки и от эха прошлого показа.
    """
    _write_json(web_box_path(out), {"url": url, "title": title, "at": at, "key": key})
