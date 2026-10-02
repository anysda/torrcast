"""A viewer of a tile the warmup holds in the queues takes its circle over and does not wait."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import pytest

import web.warm_cache as warm_cache
from torrcast.adapters.prowlarr.host_slots import HOST_SLOTS
from torrcast.usecases.select.plan import Plan
from web.warm_cache import WarmCache
from web.warm_priority import _hint

pytestmark = pytest.mark.machine


class _Hands:
    """The cache's background hands, joined by the test before it ends."""

    def __init__(self) -> None:
        self.threads: list[threading.Thread] = []

    def __call__(self, job: Callable[[], None]) -> None:
        self.threads.append(threading.Thread(target=job, daemon=True))
        self.threads[-1].start()

    def join(self) -> None:
        for thread in self.threads:
            thread.join(15.0)


@pytest.fixture(autouse=True)
def _calm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(HOST_SLOTS, "_quiet", 0.0)
    monkeypatch.setattr(HOST_SLOTS, "_calm", time.monotonic() - 100.0)
    monkeypatch.setattr(HOST_SLOTS, "_flight", {})
    monkeypatch.setattr(HOST_SLOTS, "_free", {})


def test_a_live_search_begun_in_the_warmups_first_pass_does_not_hold_the_tile() -> None:
    first = threading.Event()

    def circle(_query: str) -> list[Plan]:
        HOST_SLOTS.give_way(["RuTor"])  # pass 1: the viewer's text
        first.set()
        time.sleep(0.3)  # pass 1 answers
        HOST_SLOTS.give_way(["RuTor"])  # pass 2: the names, behind a stranger's live search
        return []

    hands = _Hands()
    cache = WarmCache(circle=circle, blurbs=lambda _p: None, spawn=hands)
    cache.ask(["x"])
    assert first.wait(1.0)

    def slow(_query: str) -> list[Plan]:
        time.sleep(2.0)  # a stranger's live search
        return []

    stranger = threading.Thread(target=lambda: cache.take("y", circle=slow))
    stranger.start()
    time.sleep(0.1)
    began = time.monotonic()
    cache.take("x", circle=lambda _q: [])
    waited = time.monotonic() - began
    stranger.join()
    hands.join()
    assert waited < 0.5, f"the viewer of x waited a stranger's live search {waited:.2f} s"


def test_a_request_in_flight_does_not_hold_the_tile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(warm_cache, "BUSY_WAIT", 3.0)  # 30 s in the product
    done = threading.Event()
    HOST_SLOTS.sent("Knaben", done)  # the last search's silent Knaben request
    late = threading.Timer(10.0, done.set)
    late.start()
    entered = threading.Event()

    def circle(_query: str) -> list[Plan]:
        entered.set()
        HOST_SLOTS.give_way(["Knaben", "RuTor"])
        return []

    hands = _Hands()
    cache = WarmCache(circle=circle, blurbs=lambda _p: None, spawn=hands)
    cache.ask(["x"])
    assert entered.wait(1.0)
    began = time.monotonic()
    cache.take("x", circle=lambda _q: [])
    waited = time.monotonic() - began
    late.cancel()
    done.set()
    late.join()
    hands.join()
    assert waited < 0.5, f"the viewer of x waited a request in flight {waited:.2f} s"


def test_the_live_take_does_not_wait_a_held_tile_either(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(warm_cache, "BUSY_WAIT", 3.0)
    done = threading.Event()
    HOST_SLOTS.sent("Knaben", done)
    entered = threading.Event()
    gone: list[float] = []

    def circle(_query: str) -> list[Plan]:
        entered.set()
        gone.append(HOST_SLOTS.give_way(["Knaben"]))
        return []

    hands = _Hands()
    cache = WarmCache(circle=circle, blurbs=lambda _p: None, spawn=hands)
    cache.ask(["x"])
    assert entered.wait(1.0)
    began = time.monotonic()
    cache.take_live("x", circle=lambda _q: [])
    waited = time.monotonic() - began
    done.set()
    hands.join()
    assert waited < 0.5, f"the live take of x waited a request in flight {waited:.2f} s"
    assert gone and gone[0] - began < 0.5, "the warmup's circle still gave way after the take"


def test_an_untaken_warmup_still_gives_way_to_a_request_in_flight() -> None:
    done = threading.Event()
    HOST_SLOTS.sent("Knaben", done)
    released = threading.Timer(0.6, done.set)
    gone: list[float] = []

    def circle(_query: str) -> list[Plan]:
        gone.append(HOST_SLOTS.give_way(["Knaben"]))
        return []

    hands = _Hands()
    cache = WarmCache(circle=circle, blurbs=lambda _p: None, spawn=hands)
    began = time.monotonic()
    released.start()
    cache.ask(["x"])
    hands.join()
    released.join()
    assert gone and gone[0] - began >= 0.5, "a warmup nobody asked for went out over the flight"


def test_an_urgent_card_does_not_wait_the_quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(HOST_SLOTS, "_quiet", 2.0)
    monkeypatch.setattr(HOST_SLOTS, "_calm", time.monotonic())
    started: list[float] = []

    def circle(_query: str) -> list[Plan]:
        started.append(time.monotonic())
        return []

    hands = _Hands()
    cache = WarmCache(circle=circle, blurbs=lambda _p: None, spawn=hands)
    began = time.monotonic()
    _hint(cache, "w", stale=True)  # the card's refresh rides the background hand
    hands.join()
    assert started and max(one - began for one in started) < 0.5, started


def test_the_background_waits_the_quiet_while_the_card_waits_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(HOST_SLOTS, "_quiet", 2.0)
    monkeypatch.setattr(HOST_SLOTS, "_calm", time.monotonic())
    started: dict[str, float] = {}

    def circle(query: str) -> list[Plan]:
        started[query] = time.monotonic()
        return []

    hands = _Hands()
    cache = WarmCache(circle=circle, blurbs=lambda _p: None, spawn=hands)
    began = time.monotonic()
    cache.ask(["bg"])
    time.sleep(0.3)
    with cache._cond:  # the background hand is up: hand the card to it, as _hint does
        cache._stale.add("card")
        cache._urgent.append("card")
    hands.join()
    lags = {key: round(at - began, 2) for key, at in started.items()}
    assert lags["card"] < 0.8 and lags["bg"] > 1.8, lags
