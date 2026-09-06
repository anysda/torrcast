"""Таблица маршрутов страницы: одна строка на маршрут."""

from __future__ import annotations

from web.box import box
from web.card import card
from web.history import history
from web.phrases import phrases
from web.position import position
from web.route import Route
from web.serve_shell import serve_shell
from web.serve_static import serve_static
from web.shelves import shelves
from web.to_tv import to_tv
from web.to_web import to_web


def routes() -> tuple[Route, ...]:
    """Все маршруты страницы; соседний заход дописывает сюда СВОЮ строку.

    Ни ``hass/serve.py``, ни :func:`web.answer_for.answer_for` про новый маршрут знать
    не обязаны: сервер спрашивает эту таблицу целиком и после своих семи маршрутов,
    которые не меняются. Строка на маршрут и запятая в конце - так соседний заход
    добавляет ``GET /api/history`` или ``POST /api/web/position``, не трогая ничьей
    чужой строки. Порядок значим ровно в одном: маршрут с ``prefix=True`` забирает всё,
    что начинается с его пути, поэтому точные пути стоят выше своих префиксов.
    """
    return (
        Route("GET", "/", serve_static),
        Route("GET", "/api/phrases", phrases),
        Route("GET", "/api/shelves", shelves),
        Route("GET", "/api/history", history),
        Route("GET", "/api/web/box", box),
        Route("POST", "/api/web/position", position),
        Route("POST", "/api/to-tv", to_tv),
        Route("POST", "/api/to-web", to_web),
        Route("GET", "/api/card/", card, prefix=True),
        Route("GET", "/card/", serve_shell, prefix=True),
        Route("GET", "/play", serve_shell),
        Route("GET", "/static/", serve_static, prefix=True),
    )
