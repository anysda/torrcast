"""The pause after a live search is waited before the warmup takes a request, not inside it."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import pytest

from torrcast.adapters.prowlarr.host_slots import HOST_SLOTS
from torrcast.usecases.select.plan import Plan
from web.warm_cache import WarmCache


class _Hands:
    """The cache's background hands, joined by the test before it ends."""

    def __init__(self) -> None:
        self.threads: list[threading.Thread] = []

    def __call__(self, job: Callable[[], None]) -> None:
        self.threads.append(threading.Thread(target=job, daemon=True))
        self.threads[-1].start()

    def join(self) -> None:
        for thread in self.threads:
            thread.join(5.0)


def _noting(began: list[float]) -> Callable[[str], list[Plan]]:
    """A circle that notes when it started and gives way as the adapter's does."""

    def circle(_query: str) -> list[Plan]:
        began.append(time.monotonic())
        HOST_SLOTS.give_way(["RuTor"])
        return []

    return circle


@pytest.mark.machine
def test_a_viewer_does_not_wait_the_warmups_quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(HOST_SLOTS, "_quiet", 2.0)
    monkeypatch.setattr(HOST_SLOTS, "_calm", time.monotonic())  # a search just ended
    entered = threading.Event()

    def circle(_query: str) -> list[Plan]:
        entered.set()
        HOST_SLOTS.give_way(["RuTor"])
        return []

    hands = _Hands()
    cache = WarmCache(circle=circle, blurbs=lambda _pictures: None, spawn=hands)
    cache.ask(["тачки"])
    entered.wait(0.3)  # the warmup's hand is up: in its circle, or waiting before it
    began = time.monotonic()
    cache.take("тачки")
    waited = time.monotonic() - began
    hands.join()
    assert waited < 0.5, f"the viewer waited the warmup's quiet {waited:.2f} s"


@pytest.mark.machine
def test_a_tile_clicked_right_after_the_search_is_not_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(HOST_SLOTS, "_quiet", 2.0)

    def circle(_query: str) -> list[Plan]:
        HOST_SLOTS.give_way(["RuTor"])
        return []

    hands = _Hands()
    cache = WarmCache(circle=circle, blurbs=lambda _pictures: None, spawn=hands)
    cache.take("тачки")  # the viewer's search; its screen asks the tiles' circles next
    cache.ask(["тачки 2006", "тачки 2 2011"])
    time.sleep(0.2)  # the viewer clicks the first tile
    began = time.monotonic()
    cache.take("тачки 2006")
    waited = time.monotonic() - began
    hands.join()
    assert waited < 0.5, f"the clicked tile waited the warmup's quiet {waited:.2f} s"


@pytest.mark.machine
def test_a_warmup_does_not_go_out_just_after_a_live_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A request cannot be taken back: the warmup that left first held the next search's host.
    monkeypatch.setattr(HOST_SLOTS, "_quiet", 0.5)
    began: list[float] = []
    hands = _Hands()
    cache = WarmCache(circle=_noting(began), blurbs=lambda _pictures: None, spawn=hands)
    cache.take("тачки")
    ended = time.monotonic()
    cache.ask(["тачки 2006"])
    hands.join()
    assert len(began) == 2, began
    assert 0.4 < began[1] - ended < 1.0, "the warmup went out on the heels of a search"


@pytest.mark.machine
def test_a_search_that_comes_puts_the_warmup_off_again(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(HOST_SLOTS, "_quiet", 0.5)
    monkeypatch.setattr(HOST_SLOTS, "_calm", time.monotonic())  # the start of the process
    began: list[float] = []
    hands = _Hands()
    cache = WarmCache(circle=_noting(began), blurbs=lambda _pictures: None, spawn=hands)
    cache.ask(["тачки 2006"])
    time.sleep(0.3)
    cache.take("тачки")
    ended = time.monotonic()
    hands.join()
    assert len(began) == 2, began
    assert 0.4 < began[1] - ended < 1.0, "the search did not put the warmup off"


def test_searches_back_to_back_do_not_keep_the_warmup_off_for_good(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(HOST_SLOTS, "_quiet", 15.0)
    monkeypatch.setattr(HOST_SLOTS, "_calm", time.monotonic())  # a search just ended
    now = time.monotonic()
    assert HOST_SLOTS.still(now) > 14.0, "the pause after a search"
    assert HOST_SLOTS.still(now - 60.0) <= 0.0, "a minute of waiting ends it"
