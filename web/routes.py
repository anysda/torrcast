"""Таблица маршрутов страницы: одна строка на маршрут."""

from __future__ import annotations

from web.phrases import phrases
from web.route import Route
from web.serve_static import serve_static


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
        Route("GET", "/static/", serve_static, prefix=True),
    )
