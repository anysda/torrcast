"""Зеркало превью поиска (TC-1126): список растёт, пока фоновый круг ещё не вернулся."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from hass.refused_error import RefusedError
from hass.search_progress import search_progress
from tests.usecases.discover.world import Indexer, row, wire_catalogue
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.facts.origin import Origin
from torrcast.domain.json_value import JsonValue
from torrcast.domain.profile import CAUTIOUS
from torrcast.usecases.discover.search_circle import search_circle

_CONFIG = Config(prowlarr_apikey="KEY")
_CARS = [
    row("Тачки / Cars (2006) BDRip 1080p | D", "a", size_gb=5.0, seeders=66),
    row("Тачки 2 / Cars 2 (2011) BDRip 1080p | D", "b", size_gb=5.0, seeders=44),
]


@pytest.fixture(autouse=True)
def _clear_jobs() -> None:
    """Реестр заходов общий на процесс: тесты не смеют путать чужой запрос со своим."""
    import hass.search_progress as module

    module._jobs.clear()


def _detect(_config: Config) -> Choice:
    return Choice(CAUTIOUS, "тест")


def _remember(*_args: Any, **_kwargs: Any) -> None:
    return None


def _as_is(results: list[JsonValue]) -> list[JsonValue]:
    """Приговор обложек без сети: фоновый круг переживает тест и не смеет звать настоящий."""
    return results


class _PreviewClient(Indexer):
    """Тот же поддельный клиент, только с ``inflight()`` - его и просит превью."""

    def __init__(self, *args: Any, raw: list[Any] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._raw = raw or []

    def inflight(self) -> list[Any]:
        return list(self._raw)


def _blocking_search(client: _PreviewClient, gate: threading.Event) -> Any:
    """Круг поиска, который отдаёт клиента сразу и не возвращается, пока не отпустят."""

    def search(config: Config, args: Any, said: Any, profile: Any, on_indexer: Any) -> Any:
        on_indexer(client)
        gate.wait(2.0)
        return search_circle(
            config,
            args,
            said,
            profile,
            indexer=lambda *_a, **_k: client,
            passport=lambda *_a, **_k: Origin(),
        )

    return search


def _poll(text: str, search: Any) -> tuple[list[Any], bool]:
    return search_progress(_CONFIG, text, _detect, _remember, search=search, offer=_as_is)


def test_a_still_running_job_answers_with_a_preview_before_the_circle_returns() -> None:
    """🔴 Ядро карточки: находка первого ответившего видна ДО конца круга."""
    wire_catalogue()
    gate = threading.Event()
    client = _PreviewClient(answers={"тачки": _CARS}, raw=_CARS)
    search = _blocking_search(client, gate)
    try:
        results, partial = _poll("тачки", search)
        deadline = time.monotonic() + 1.0
        while not results and time.monotonic() < deadline:
            results, partial = _poll("тачки", search)

        assert partial is True, "круг ещё держит клиент за шлагбаумом"
        assert [hit["title"] for hit in results] == ["Тачки", "Тачки 2"]
        assert all(hit["default"] is False for hit in results), (
            "превью не решает за отбор, кто взят по умолчанию (TC-1126)"
        )
    finally:
        gate.set()


def test_the_final_poll_carries_the_real_default_and_partial_false() -> None:
    wire_catalogue()
    gate = threading.Event()
    gate.set()  # круг возвращается сразу же
    client = _PreviewClient(answers={"тачки": _CARS}, raw=_CARS)
    search = _blocking_search(client, gate)

    results, partial = _poll("тачки", search)
    deadline = time.monotonic() + 1.0
    while partial and time.monotonic() < deadline:
        results, partial = _poll("тачки", search)

    assert partial is False
    assert len(results) == 2
    assert sum(1 for hit in results if hit["default"]) == 1


def test_the_final_list_goes_through_the_same_poster_verdict_as_plain_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Веб-выдача шла без обложек: итог не проходил приговор, который проходит HA."""
    wire_catalogue()
    gate = threading.Event()
    gate.set()
    client = _PreviewClient(answers={"тачки": _CARS}, raw=_CARS)
    search = _blocking_search(client, gate)
    monkeypatch.setattr(
        "hass.searching.OFFER",
        lambda results: [{**hit, "poster": "p-" + hit["key"]} for hit in results],
    )

    def poll() -> tuple[list[Any], bool]:
        return search_progress(_CONFIG, "тачки", _detect, _remember, search=search)

    results, partial = poll()
    deadline = time.monotonic() + 1.0
    while partial and time.monotonic() < deadline:
        results, partial = poll()

    assert partial is False
    assert [hit["poster"] for hit in results] == ["p-" + hit["key"] for hit in results]
    assert len(results) == 2


def test_a_second_poll_of_the_same_query_does_not_start_a_second_search() -> None:
    wire_catalogue()
    gate = threading.Event()
    gate.set()
    client = _PreviewClient(answers={"тачки": _CARS}, raw=_CARS)
    calls: list[int] = []

    def search(config: Config, args: Any, said: Any, profile: Any, on_indexer: Any) -> Any:
        calls.append(1)
        on_indexer(client)
        return search_circle(
            config,
            args,
            said,
            profile,
            indexer=lambda *_a, **_k: client,
            passport=lambda *_a, **_k: Origin(),
        )

    _results, partial = _poll("тачки", search)
    deadline = time.monotonic() + 1.0
    while partial and time.monotonic() < deadline:
        _results, partial = _poll("тачки", search)
    _poll("тачки", search)
    _poll("тачки", search)

    assert len(calls) == 1, "тот же запрос второй раз индексеров не тревожит"


def test_a_refusal_surfaces_only_once_the_job_is_done() -> None:
    wire_catalogue()
    gate = threading.Event()
    client = _PreviewClient(answers={}, raw=[])
    search = _blocking_search(client, gate)

    results, partial = _poll("нетакого", search)
    assert (results, partial) == ([], True), "отказ ещё не готов - это просто пустой ход"

    gate.set()
    deadline = time.monotonic() + 1.0
    refused: RefusedError | None = None
    while time.monotonic() < deadline:
        try:
            _poll("нетакого", search)
        except RefusedError as caught:
            refused = caught
            break
    assert refused is not None and "нетакого" in refused.word
