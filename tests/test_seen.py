"""``POST /api/seen``: экран плиток от страницы доезжает до прогрева разобранным."""

from __future__ import annotations

import json

import pytest

import web.seen
from torrcast.domain.json_value import JsonValue
from web.answer import Answer
from web.request import Request
from web.seen import seen
from web.warm_cache import WarmCache


class _Heard:
    """Прогрев-заглушка: помнит экран, который ему назвали, и ни во что не ходит."""

    def __init__(self) -> None:
        self.screens: list[list[str]] = []

    def ask(self, screen: list[str]) -> int:
        self.screens.append(list(screen))
        return len(screen)


def _post(body: dict[str, JsonValue], monkeypatch: pytest.MonkeyPatch) -> tuple[_Heard, Answer]:
    heard = _Heard()
    monkeypatch.setattr(web.seen, "WARM", heard)
    return heard, seen(Request(method="POST", path="/api/seen", query={}, body=body))


def test_the_screen_the_page_sees_reaches_the_warmer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Страница называет запросы своих плиток - прогрев получает ровно их."""
    rows: JsonValue = ["kin", "Ludwig"]

    heard, answer = _post({"tiles": rows}, monkeypatch)

    assert heard.screens == [["kin", "Ludwig"]]
    assert json.loads(answer.body) == {"queued": 2}


def test_a_body_without_a_screen_is_refused_and_nothing_is_warmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Тело не про экран - отказ: греть наугад дороже, чем не греть вовсе."""
    heard, answer = _post({"tiles": "kin"}, monkeypatch)

    assert answer.code == 400
    assert heard.screens == []


def test_rows_that_are_not_queries_are_left_at_the_door(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Строка запроса - всё, что прогрев понимает; прочее не доезжает до круга."""
    rows: JsonValue = ["kin", 12, {"query": "kin"}, None]

    heard, _answer = _post({"tiles": rows}, monkeypatch)

    assert heard.screens == [["kin"]]


def test_an_empty_screen_is_a_lawful_word_and_clears_the_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """«Плиток не видно» - тоже слово: так снимается очередь прошлого экрана."""
    heard, answer = _post({"tiles": []}, monkeypatch)

    assert heard.screens == [[]]
    assert json.loads(answer.body) == {"queued": 0}


def test_the_answer_speaks_the_number_the_warmer_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Число в ответе - от прогрева, а не от длины тела: у выдачи круг один на экран."""
    cache = WarmCache(circle=lambda _q: [], blurbs=lambda _p: None, spawn=lambda job: job())
    monkeypatch.setattr(web.seen, "WARM", cache)
    rows: JsonValue = ["kin" for _ in range(5)]

    answer = seen(Request(method="POST", path="/api/seen", query={}, body={"tiles": rows}))

    assert json.loads(answer.body) == {"queued": 1}
