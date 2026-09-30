"""Проверяет маршрут ``GET /api/shelves``: тело - ровно то, что отдал кэш."""

from __future__ import annotations

import json

import pytest

import web.shelves as shelves_module
from hass.hit_posters import hits
from hass.shelf_posters import ShelfPosters
from torrcast.domain.json_value import JsonValue
from web.request import Request
from web.shelves import shelves


class _FakeCache:
    def __init__(
        self, body: dict[str, JsonValue], filling: bool = False, settling: bool = False
    ) -> None:
        self._body = body
        self.filling = filling
        self.settling = settling

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
    # Собранные полки метки недоехавшего ответа не несут - переспрашивать нечего.
    assert answer.extra == ()


def test_an_unbuilt_cache_marks_the_answer_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Фон ни разу не собрал полки (``built_at`` пуст) - страница переспросит сама."""
    body: dict[str, JsonValue] = {"fresh": [], "popular": [], "built_at": None}
    monkeypatch.setattr(shelves_module, "_cache", _FakeCache(body))

    answer = shelves(Request("GET", "/api/shelves", {}, {}))

    assert answer.code == 200
    assert ("X-Torrcast-Partial", "1") in answer.extra


def test_the_shelves_take_only_covers_whose_bytes_are_here() -> None:
    """Сборка полок ждёт байты обложек: плитка главной не держит соединение браузера."""
    assert shelves_module._cache.offer == hits.settled


def test_a_shown_but_still_filling_shelf_keeps_the_answer_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Холодный заход уже показал плитки, но обложки ещё едут: счётчик страницы не гаснет."""
    body: dict[str, JsonValue] = {"fresh": [], "popular": [], "built_at": "2026-09-30T00:00:00"}
    monkeypatch.setattr(shelves_module, "_cache", _FakeCache(body, filling=True, settling=True))

    answer = shelves(Request("GET", "/api/shelves", {}, {}))

    assert ("X-Torrcast-Partial", "1") in answer.extra
    assert ("X-Torrcast-Settling", "1") in answer.extra


def test_a_full_shelf_under_verdicts_is_settling_but_not_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Полки полны, приговоры ещё идут: страница переспрашивает, но счётчик уже снят."""
    body: dict[str, JsonValue] = {"fresh": [], "popular": [], "built_at": "2026-09-30T00:00:00"}
    monkeypatch.setattr(shelves_module, "_cache", _FakeCache(body, settling=True))

    answer = shelves(Request("GET", "/api/shelves", {}, {}))

    assert answer.extra == (("X-Torrcast-Settling", "1"),)


def test_a_cold_build_shows_covers_as_they_land_and_judges_in_parallel() -> None:
    """Холодный заход: быстрый путь обложек поиска и несколько рук приговоров."""
    cache = shelves_module._cache
    posters = shelves_module._POSTERS
    assert posters == ShelfPosters(hits)
    wired = (cache.ask, cache.landed, cache.arriving)
    assert wired == (posters.ask, posters.landed, posters.arriving)
    assert cache.early
    assert cache.workers > 1
