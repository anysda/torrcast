"""Checks that the blocking search judges its tiles as soon as the viewer's text is in."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import pytest

from hass.early_verdict import early_verdict
from hass.searching import searching
from tests.test_search_progress import _PreviewClient
from tests.test_searching import _CARS, _CONFIG, _cautious, _search
from tests.usecases.discover.world import Indexer, wire_catalogue
from torrcast.domain.json_value import JsonValue
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
from torrcast.usecases.discover.named_round import NamedRound

pytestmark = pytest.mark.machine


def _judged() -> tuple[list[list[JsonValue]], threading.Event, Callable[..., list[JsonValue]]]:
    said: list[list[JsonValue]] = []
    done = threading.Event()

    def offer(records: list[JsonValue]) -> list[JsonValue]:
        said.append(records)
        done.set()
        return records

    return said, done, offer


def _ahead() -> NamedRound:
    round_ = NamedRound(_PreviewClient(raw=_CARS))
    round_.ahead = True
    return round_


def test_the_verdict_waits_for_the_viewers_text_and_runs_once() -> None:
    wire_catalogue()
    said, done, offer = _judged()
    round_ = _ahead()
    hook = early_verdict("тачки", offer)
    hook(round_)
    hook(round_)
    assert not done.wait(0.2), "judged before the viewer's text answered"
    round_.typed.set()
    assert done.wait(2.0), "the viewer's text answered, and nothing was judged"
    done.clear()
    assert not done.wait(0.2), "a second hook call judged the list again"
    assert len(said) == 1
    assert "Тачки 2" in [record["title"] for record in said[0] if isinstance(record, dict)]


def test_a_plain_client_is_left_to_the_lists_own_verdict() -> None:
    _said, done, offer = _judged()
    early_verdict("тачки", offer)(Indexer())
    assert not done.wait(0.2)


def test_a_viewers_text_answered_last_is_left_to_the_lists_own_verdict() -> None:
    wire_catalogue()
    _said, done, offer = _judged()
    round_ = NamedRound(_PreviewClient(raw=_CARS))
    early_verdict("тачки", offer)(round_)
    round_.typed.set()
    assert not done.wait(0.3), "judged beside nothing, racing the list's own build"


def test_the_blocking_search_judges_before_its_circle_returns() -> None:
    wire_catalogue()
    _said, done, offer = _judged()
    before: list[bool] = []

    def search(*said: Any, on_indexer: Callable[[IndexerClient], None] | None = None) -> Any:
        round_ = _ahead()
        assert on_indexer is not None, "the circle got no hook"
        on_indexer(round_)
        round_.typed.set()
        before.append(done.wait(2.0))
        return _search(*said)

    searching(_CONFIG, "тачки", search, _cautious, lambda *_: None, offer)
    assert before == [True], "the verdict waited for the whole circle"
