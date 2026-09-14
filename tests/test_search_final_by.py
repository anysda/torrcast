"""Срок финала поиска: опрос получает финал к сроку сервера, даже если круг или приговор идут."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

import hass.search_progress as module
from hass.search_job import FINAL_BY
from hass.search_progress import search_progress
from tests.test_search_progress import (
    _CARS,
    _CONFIG,
    _as_is,
    _blocking_search,
    _catalog,
    _detect,
    _PreviewClient,
    _remember,
)
from tests.usecases.discover.world import wire_catalogue
from torrcast.domain.json_value import JsonValue


@pytest.fixture(autouse=True)
def _clear_jobs() -> None:
    module._jobs.clear()


def _age(query: str) -> None:
    """Заход прожил свой срок: часы не ждём, а отводим начало захода на сам срок назад."""
    module._jobs[query.casefold()].started_at -= FINAL_BY


def _titles(results: list[Any]) -> list[tuple[str, Any]]:
    return [(hit["title"], hit.get("dim")) for hit in results]


def test_a_circle_past_the_deadline_gives_the_poll_a_final_from_what_came() -> None:
    """Круг не вернулся к сроку: финал из пришедшего, каталог без раздач гаснет, круг дописывает."""
    wire_catalogue()
    gate = threading.Event()
    client = _PreviewClient(answers={"тачки": _CARS}, raw=_CARS[:1])
    search = _blocking_search(client, gate)
    catalog = _catalog(("tt2", "movie", "Nope", "2001", "Нетакого тачки"))

    def poll() -> tuple[list[Any], bool]:
        return search_progress(
            _CONFIG, "тачки", _detect, _remember, search=search, offer=_as_is, catalog=catalog
        )

    try:
        results, partial = poll()
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and len(results) < 2:
            results, partial = poll()
        assert partial is True
        assert _titles(results) == [("Нетакого тачки", None), ("Тачки", None)]
        _age("тачки")
        results, partial = poll()
        assert partial is False, "срок прошёл: опрос обязан получить финал, а не ещё одно превью"
        assert _titles(results) == [("Нетакого тачки", True), ("Тачки", None)]
    finally:
        gate.set()
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and len(results) < 3:
        results, partial = poll()
    assert partial is False
    assert len(results) == 3, "досчитанный круг заменяет финал к сроку для следующего захода"


def test_a_poster_verdict_past_the_deadline_does_not_hold_the_final() -> None:
    """Круг вернулся, приговор обложек молчит: к сроку финал - список круга без его обложек."""
    wire_catalogue()
    verdict = threading.Event()
    judged: list[int] = []

    def offer(results: list[JsonValue]) -> list[JsonValue]:
        judged.append(len(results))
        verdict.wait(3.0)
        return [{**hit, "poster": "p.jpg"} for hit in results if isinstance(hit, dict)]

    client = _PreviewClient(answers={"тачки": _CARS}, raw=[])
    opened = threading.Event()
    opened.set()
    search = _blocking_search(client, opened)

    def poll() -> tuple[list[Any], bool]:
        return search_progress(_CONFIG, "тачки", _detect, _remember, search=search, offer=offer)

    try:
        results, partial = poll()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not module._jobs["тачки"].hits:
            results, partial = poll()
        assert partial is True, "приговор идёт, срок не прошёл: финала ещё нет"
        _age("тачки")
        results, partial = poll()
        assert partial is False
        assert [title for title, _ in _titles(results)] == ["Тачки", "Тачки 2"]
        assert not any(hit.get("poster") for hit in results)
    finally:
        verdict.set()
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and not all(hit.get("poster") for hit in results):
        results, partial = poll()
    assert [hit.get("poster") for hit in results] == ["p.jpg", "p.jpg"]
