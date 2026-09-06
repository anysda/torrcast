"""Отдача оболочки страницы для маршрутов клиентского роутера (``/card/*``)."""

from __future__ import annotations

from web.answer import Answer
from web.request import Request
from web.serve_static import KINDS, STATIC


def serve_shell(_request: Request) -> Answer:
    """Тот же ``index.html``, что и на ``/``: адрес карточки разбирает JS в браузере.

    Маршрут держит адресную строку осмысленной (``/card/tt0816692``) без второго
    сервера истории: страница одна, а какой экран собрать по ней, решает ``app.js``.
    """
    found = STATIC / "index.html"
    return Answer(200, found.read_bytes(), KINDS[".html"])
