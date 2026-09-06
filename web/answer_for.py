"""Единственный вход сервера в маршруты страницы."""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import parse_qs, unquote

from torrcast.domain.json_value import JsonValue
from web.answer import Answer
from web.request import Request
from web.routes import routes


def answer_for(method: str, target: str, body: Mapping[str, JsonValue] | None) -> Answer | None:
    """Ответ страницы на запрос или ``None``, если путь не её.

    ``None`` тут не ошибка, а слово «не моё»: сервер моста отвечает на такой путь ровно
    тем же 404, каким отвечал до появления страницы. Тело нужно только маршрутам POST,
    и читает его сервер: сокет читается один раз, и делать это дважды нечем.
    """
    path, _, asked = target.partition("?")
    path = unquote(path)
    request = Request(method, path, _query(asked), body or {})
    for route in routes():
        if route.takes(method, path):
            return route.answer(request)
    return None


def _query(asked: str) -> dict[str, str]:
    """Доводы запроса первым значением: ``?lang=ru&lang=en`` - это один язык, не два."""
    return {name: values[0] for name, values in parse_qs(asked).items() if values}
