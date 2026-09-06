"""Таблица маршрутов страницы: соседний заход дописывает сюда свою строку."""

from __future__ import annotations

from web.routes import routes


def test_the_page_and_its_files_and_its_words_are_all_here() -> None:
    named = {(route.method, route.path) for route in routes()}

    assert ("GET", "/") in named
    assert ("GET", "/api/phrases") in named
    assert ("GET", "/static/") in named


def test_no_two_routes_answer_the_same_call() -> None:
    named = [(route.method, route.path) for route in routes()]

    assert sorted(named) == sorted(set(named))


def test_a_prefix_never_stands_above_an_exact_path_it_would_swallow() -> None:
    """Порядок в таблице значим: префикс выше точного пути молча съел бы его."""
    table = routes()
    swallowed = [
        (early.path, late.path)
        for number, early in enumerate(table)
        if early.prefix
        for late in table[number + 1 :]
        if late.method == early.method and late.path.startswith(early.path)
    ]

    assert swallowed == []


def test_every_route_names_a_method_the_bridge_speaks() -> None:
    strangers = [route.path for route in routes() if route.method not in ("GET", "POST")]

    assert strangers == []
