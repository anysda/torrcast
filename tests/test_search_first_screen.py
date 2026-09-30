"""Первый ряд выдачи встаёт вместе с обложками своих плиток (стенд: 8 из 8 первых тел пустые)."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

import hass.search_progress as module
from hass.hit_posters import HitPosters
from hass.poster_shelf import PosterShelf
from hass.search_first_screen import FIRST_SCREEN_BY
from hass.search_progress import search_progress
from tests.test_search_progress import (
    _CARS,
    _CONFIG,
    _blocking_search,
    _detect,
    _PreviewClient,
    _remember,
)
from tests.usecases.discover.world import wire_catalogue


@pytest.fixture(autouse=True)
def _clear_jobs() -> None:
    module._jobs.clear()


class _Source:
    """Источник обложек, который называет адрес каждой картине и отдаёт байты по команде."""

    def __init__(self) -> None:
        self.bytes_go = threading.Event()

    def wanted(self, asks: Any, _timeout: float) -> dict[Any, list[str]]:
        return {ask: ["https://img/" + ask.title] for ask in asks}

    def bodies(self, wanted: Any, _timeout: float) -> dict[Any, bytes]:
        self.bytes_go.wait(3.0)
        return dict.fromkeys(wanted, b"poster")


def _poller(tmp_path: Path, source: Any, gate: threading.Event) -> Any:
    search = _blocking_search(_PreviewClient(answers={"тачки": _CARS}, raw=_CARS), gate)
    posters = HitPosters(source=source, shelf=PosterShelf(home=lambda: tmp_path))

    def poll() -> tuple[list[Any], bool]:
        return search_progress(
            _CONFIG,
            "тачки",
            _detect,
            _remember,
            search=search,
            offer=posters.urgent,
            covers=posters,
        )

    return poll


def _until(poll: Any, seconds: float) -> tuple[list[Any], float]:
    """Опрашивать шагом страницы, пока не придёт ряд; ряд и секунды от первого опроса."""
    began = time.monotonic()
    results: list[Any] = []
    while not results and time.monotonic() - began < seconds:
        results, _partial = poll()
        if not results:
            threading.Event().wait(0.02)
    return results, time.monotonic() - began


def test_the_first_row_waits_for_its_covers_and_comes_with_them(tmp_path: Path) -> None:
    """🔴 Ядро: ряд не выходит серым, пока байты его обложек в пути, и выходит с ними."""
    wire_catalogue()
    source, gate = _Source(), threading.Event()
    poll = _poller(tmp_path, source, gate)
    try:
        held, _spent = _until(poll, FIRST_SCREEN_BY / 3)
        assert held == [], "ряд вышел раньше своих обложек"
        source.bytes_go.set()
        results, spent = _until(poll, FIRST_SCREEN_BY)
        assert [hit["title"] for hit in results] == ["Тачки", "Тачки 2"]
        assert all(hit.get("poster") for hit in results), "ряд вышел без легших обложек"
        assert spent < FIRST_SCREEN_BY / 2, "ряд ждал срока, а не своих обложек"
    finally:
        source.bytes_go.set()
        gate.set()


def test_a_stuck_cover_holds_the_first_row_only_until_the_deadline(tmp_path: Path) -> None:
    """Застрявший источник стоит человеку не больше срока: ряд выходит без его обложки."""
    wire_catalogue()
    source, gate = _Source(), threading.Event()
    poll = _poller(tmp_path, source, gate)
    try:
        results, spent = _until(poll, FIRST_SCREEN_BY + 1.0)
        assert [hit["title"] for hit in results] == ["Тачки", "Тачки 2"]
        assert [hit.get("poster") for hit in results] == [None, None]
        assert FIRST_SCREEN_BY - 0.1 <= spent < FIRST_SCREEN_BY + 0.5, spent
    finally:
        source.bytes_go.set()
        gate.set()


def test_a_drawn_row_is_never_taken_off_screen_again(tmp_path: Path) -> None:
    """Однажды показанный ряд не пропадает, даже когда новые обложки снова в пути."""
    wire_catalogue()
    source, gate = _Source(), threading.Event()
    poll = _poller(tmp_path, source, gate)
    try:
        results, _spent = _until(poll, FIRST_SCREEN_BY + 1.0)
        assert results
        job = module._jobs["тачки"]
        job.posters.clear()
        job.started_at = time.monotonic()
        assert len(poll()[0]) == 2, "показанный ряд снова придержан"
    finally:
        source.bytes_go.set()
        gate.set()
