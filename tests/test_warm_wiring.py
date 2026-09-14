"""Проводка прогрева: один предмет на процесс и боевые службы за его тремя швами."""

from __future__ import annotations

import threading
import time

import pytest

import web.warm_wiring as wiring
from torrcast.usecases.facts import FactPicture
from web.warm_cache import TTL, WORKERS, WarmCache


def test_the_process_gets_one_assembled_warmer() -> None:
    """Единственное место, где прогрев видит свои службы, - эта проводка."""
    assert isinstance(wiring.WARM, WarmCache)
    assert wiring.WARM.circle == wiring.TARGETS.search
    assert wiring.TARGETS.circle is wiring._search
    assert wiring.TARGETS.ask == wiring.WARM.ask
    assert wiring.WARM.blurbs is wiring._blurbs
    assert wiring.WARM.spawn is wiring._daemon


def test_the_live_warmer_keeps_the_measured_policy() -> None:
    """Мера прогрева названа числами в одном месте, и проводка их не переписывает."""
    assert wiring.WARM.ttl == TTL
    assert wiring.WARM.workers == WORKERS
    assert wiring.WARM.clock is time.monotonic


def test_the_background_hand_holds_nobody_at_the_exit() -> None:
    """Фон боевого прогрева - демон: выход из процесса он не задерживает."""
    seen: list[threading.Thread] = []
    done = threading.Event()

    started = threading.enumerate()
    wiring._daemon(done.set)
    assert done.wait(5.0)
    seen.extend(hand for hand in threading.enumerate() if hand not in started)

    for hand in seen:
        hand.join(5.0)
    assert all(hand.daemon for hand in seen)


def test_home_related_warmup_waits_for_its_fact_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    """The startup facts own the HTTP lanes until their final batch has settled."""
    order: list[str] = []

    class _Done:
        @staticmethod
        def wait() -> None:
            order.append("settled")

    class _Facts:
        _done = _Done()

        def __init__(self, pictures: object) -> None:
            assert pictures == [("Одиссея", 2026, "movie")]

        def start(self) -> None:
            order.append("start")

        def finish(self) -> None:
            order.append("finish")

    monkeypatch.setattr(wiring, "MenuFacts", _Facts)
    monkeypatch.setattr(wiring, "prime", lambda _related, _pictures: order.append("related"))
    monkeypatch.setattr(wiring, "_daemon", lambda job: job())

    wiring._prime_screen([("Одиссея", 2026, "movie")])

    assert order == ["start", "finish", "settled", "start", "finish", "settled", "related"]


def test_home_warmup_leaves_three_wikimedia_lanes_for_a_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A persisted screen starts no more than two facts in one source wave."""
    batches: list[list[object]] = []

    class _Done:
        @staticmethod
        def wait() -> None:
            return None

    class _Facts:
        _done = _Done()

        def __init__(self, pictures: list[object]) -> None:
            batches.append(pictures)

        def start(self) -> None:
            return None

        def finish(self) -> None:
            return None

    pictures: list[FactPicture] = [(f"Film {at}", 2020 + at, "movie") for at in range(5)]
    monkeypatch.setattr(wiring, "MenuFacts", _Facts)
    monkeypatch.setattr(wiring, "prime", lambda _related, _pictures: None)
    monkeypatch.setattr(wiring, "_daemon", lambda job: job())

    wiring._prime_screen(pictures)

    assert batches == [
        pictures[:2],
        pictures[:2],
        pictures[2:4],
        pictures[2:4],
        pictures[4:],
        pictures[4:],
    ]
