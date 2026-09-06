"""Одна строка таблицы маршрутов: кто отвечает и на что."""

from __future__ import annotations

from web.answer import Answer
from web.request import Request
from web.route import Route


def _stub(request: Request) -> Answer:
    return Answer(200, request.path.encode())


def test_an_exact_route_takes_only_its_own_path() -> None:
    route = Route("GET", "/api/phrases", _stub)

    assert route.takes("GET", "/api/phrases")
    assert not route.takes("GET", "/api/phrases/ru")
    assert not route.takes("GET", "/api/phrase")


def test_a_prefix_route_takes_everything_under_it() -> None:
    route = Route("GET", "/static/", _stub, prefix=True)

    assert route.takes("GET", "/static/style.css")
    assert route.takes("GET", "/static/fonts/archivo.css")
    assert not route.takes("GET", "/static")


def test_a_route_answers_its_own_method_only() -> None:
    route = Route("POST", "/api/web/position", _stub)

    assert route.takes("POST", "/api/web/position")
    assert not route.takes("GET", "/api/web/position")


def test_the_handler_is_the_one_that_answers() -> None:
    route = Route("GET", "/", _stub)

    assert route.answer(Request("GET", "/", {}, {})).body == b"/"
