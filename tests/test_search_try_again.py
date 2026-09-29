"""«Try again» after a failed search asks for a circle, not for the echo of the failure."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest

import hass.search_progress as module
from hass.refused_error import RefusedError
from hass.search_job import REFUSAL_BY
from hass.search_progress import search_progress
from tests.test_warm_cache import _PLAN
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.nothing_found_error import NothingFoundError
from torrcast.domain.profile import CAUTIOUS
from torrcast.usecases.discover.told_circle import ToldCircle
from web.warm_cache import WarmCache

_FAILED = {"key": "web.search.failed", "values": {}}


@pytest.fixture(autouse=True)
def _clear_jobs() -> Iterator[None]:
    module._jobs.clear()
    yield
    for thread in threading.enumerate():
        if thread.name == "search-progress":
            thread.join(5.0)


def _poll(search: Any, warm: WarmCache) -> tuple[list[Any], bool]:
    return search_progress(
        Config(prowlarr_apikey="KEY"),
        "Начало",
        lambda _config: Choice(CAUTIOUS, "тест"),
        lambda *_a, **_k: None,
        search=search,
        offer=lambda results: results,
        warm=warm,
    )


def _warm() -> WarmCache:
    return WarmCache(
        lambda _q: [], lambda _p: None, lambda job: threading.Thread(target=job).start()
    )


def _until(search: Any, warm: WarmCache) -> tuple[list[Any], bool]:
    deadline = time.monotonic() + 3.0
    said = _poll(search, warm)
    while said[1] and time.monotonic() < deadline:
        time.sleep(0.02)
        said = _poll(search, warm)
    return said


def test_try_again_past_the_listening_window_joins_the_circle_still_running() -> None:
    """🔴 Between 45 and 60 s «Try again» got the same «Search failed» at once, no circle."""
    gate = threading.Event()
    circles: list[str] = []

    def search(*_args: Any) -> Any:
        circles.append("asked")
        gate.wait(3.0)
        return ToldCircle([_PLAN], [], whole=True)

    warm = _warm()
    try:
        assert _poll(search, warm) == ([], True)
        module._jobs["начало"].started_at -= REFUSAL_BY + 1.0
        with pytest.raises(RefusedError) as failed:
            _poll(search, warm)
        assert failed.value.body()["reason"] == _FAILED, "the page stopped listening"

        assert _poll(search, warm)[1] is True, "«Try again» waits for a circle, not an echo"
    finally:
        gate.set()
    results, partial = _until(search, warm)
    assert (len(results), partial) == (1, False)
    assert circles == ["asked"], "the running circle is joined, not doubled"


def test_try_again_after_a_cut_empty_circle_asks_the_catalogue_anew() -> None:
    """A cut refusal the memory keeps a minute for the cards is no answer to someone asking."""
    answers: list[Any] = [NothingFoundError("пусто"), ToldCircle([_PLAN], [], whole=True)]
    circles: list[str] = []

    def search(*_args: Any) -> Any:
        circles.append("asked")
        answer = answers[len(circles) - 1]
        if isinstance(answer, NothingFoundError):
            raise answer  # whole is False: someone kept silent
        return answer

    warm = _warm()
    with pytest.raises(RefusedError) as failed:
        _until(search, warm)
    assert failed.value.body()["reason"] == _FAILED

    results, partial = _until(search, warm)
    assert (len(results), partial) == (1, False)
    assert circles == ["asked", "asked"]
