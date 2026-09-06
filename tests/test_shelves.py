"""Проверяет маршрут ``GET /api/shelves``: тело - ровно то, что отдал кэш."""

from __future__ import annotations

import json

import pytest

import web.shelves as shelves_module
from torrcast.domain.json_value import JsonValue
from web.request import Request
from web.shelves import shelves


class _FakeCache:
    def __init__(self, body: dict[str, JsonValue]) -> None:
        self._body = body

    def get(self) -> dict[str, JsonValue]:
        return self._body


def test_the_route_answers_with_exactly_what_the_cache_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Маршрут не считает ничего сам - тело ответа буквально то, что вернул кэш."""
    body: dict[str, JsonValue] = {
        "fresh": [],
        "popular": [],
        "built_at": "2026-09-06T00:00:00+00:00",
    }
    monkeypatch.setattr(shelves_module, "_cache", _FakeCache(body))

    answer = shelves(Request("GET", "/api/shelves", {}, {}))

    assert answer.code == 200
    assert json.loads(answer.body) == body
    assert answer.kind == "application/json; charset=utf-8"
