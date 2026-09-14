"""Проводка прогрева: один предмет на процесс и боевые службы за его тремя швами."""

from __future__ import annotations

import threading
import time

import pytest

import web.warm_wiring as wiring
from torrcast.domain.facts.fact import Fact
from torrcast.runtime.facts_wiring import FACTS
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


def test_a_hovered_tile_starts_its_shelf_from_the_shared_fact_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hover never repeats Wikipedia just to turn an article into a QID."""
    called: list[tuple[str, bool, str]] = []

    class _Facts:
        def ready(self, _title: str, _year: int) -> Fact:
            return Fact(entity="Q8337")

        def watch(self, callback: object) -> None:
            assert callable(callback)

    class _Flights:
        @staticmethod
        def of(_title: str, _year: int, _kind: str, foreground: bool = True) -> _Facts:
            assert not foreground
            return _Facts()

    class _Related:
        @staticmethod
        def of(title: str, series: bool, entity: str) -> None:
            called.append((title, series, entity))

    monkeypatch.setattr(wiring, "_facts", _Flights())
    monkeypatch.setattr(wiring, "RELATED", _Related())

    wiring._kin(("Гарри Поттер", 2001, "movie"))

    assert called == [("Гарри Поттер", False, "Q8337")]


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


def test_home_warmup_starts_no_passport_for_a_confirmed_missing_article(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tile without an article shows no franchise; only a silent fact gets a shelf lookup."""
    primed: list[list[FactPicture]] = []
    found = {"Без статьи": Fact(missing=True), "Молчит": Fact()}

    class _Done:
        @staticmethod
        def wait() -> None:
            return None

    class _Facts:
        _done = _Done()

        def __init__(self, _pictures: object) -> None:
            return None

        def start(self) -> None:
            return None

        def finish(self) -> None:
            return None

        @staticmethod
        def ready(title: str, _year: int | None) -> Fact:
            return found[title]

    monkeypatch.setattr(wiring, "MenuFacts", _Facts)
    monkeypatch.setattr(wiring, "prime", lambda _related, pictures: primed.append(pictures))
    monkeypatch.setattr(wiring, "_daemon", lambda job: job())

    wiring._prime_screen([("Без статьи", 1991, "movie"), ("Молчит", 1992, "movie")])

    assert primed == [[("Молчит", 1992, "movie")]]


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


def test_a_visible_tile_with_a_confirmed_missing_article_gets_no_franchise_passport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The visible lane skips the passport a missing article never uses; a silent fact keeps it."""
    finished: list[list[FactPicture]] = []
    stored = {("Без статьи", 1991): Fact(missing=True)}

    class _Cache:
        @staticmethod
        def blurbs(wanted: list[tuple[str, int | None]]) -> dict[tuple[str, int | None], Fact]:
            return {key: stored[key] for key in wanted if key in stored}

    class _Related:
        @staticmethod
        def finish(pictures: list[FactPicture]) -> None:
            finished.append(pictures)

    monkeypatch.setattr(FACTS, "cache", _Cache())
    monkeypatch.setattr(wiring, "RELATED", _Related())

    wiring._background_kin(("Без статьи", 1991, "movie"))
    wiring._background_kin(("Молчит", 1992, "movie"))

    assert finished == [[("Молчит", 1992, "movie")]]
