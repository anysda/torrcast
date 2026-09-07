"""Проверяет маршрут ``GET /api/web/sources``: тело - ровно то, что отдал кэш."""

from __future__ import annotations

import json

import pytest

import web.sources as sources_module
from web.request import Request
from web.sources import sources


class _FakeCache:
    def __init__(self, value: int) -> None:
        self._value = value

    def get(self) -> int:
        return self._value


def test_the_route_answers_with_exactly_what_the_cache_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Маршрут не считает ничего сам - тело ответа буквально то число, что вернул кэш."""
    monkeypatch.setattr(sources_module, "_cache", _FakeCache(7))

    answer = sources(Request("GET", "/api/web/sources", {}, {}))

    assert answer.code == 200
    assert json.loads(answer.body) == {"count": 7}
    assert answer.kind == "application/json; charset=utf-8"
