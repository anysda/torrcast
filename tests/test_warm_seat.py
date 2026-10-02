"""The viewer who takes a warmup circle over gets the clients it handed its watchers."""

from __future__ import annotations

import threading
import time

import pytest

from tests.test_search_progress import _PreviewClient
from tests.test_warm_adopt import _Hands
from torrcast.adapters.prowlarr.host_slots import HOST_SLOTS
from torrcast.adapters.prowlarr.warmup import TAKEN, warmup
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
from torrcast.usecases.discover.named_round import NamedRound
from torrcast.usecases.select.plan import Plan
from web.warm_cache import WarmCache
from web.warm_seat import WarmSeat


@pytest.fixture(autouse=True)
def _calm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(HOST_SLOTS, "_quiet", 0.0)
    monkeypatch.setattr(HOST_SLOTS, "_calm", time.monotonic() - 100.0)
    monkeypatch.setattr(HOST_SLOTS, "_flight", {})
    monkeypatch.setattr(HOST_SLOTS, "_free", {})


def _round() -> NamedRound:
    return NamedRound(_PreviewClient())


def test_the_hook_gets_the_clients_built_before_and_after_the_take() -> None:
    seat, built, later = WarmSeat(), _round(), _round()
    seen: list[IndexerClient] = []
    with warmup(seat):
        WarmSeat.relay(built)
    with WarmSeat.watching(seen.append):
        seat.take()
    with warmup(seat):
        WarmSeat.relay(later)
    assert (seat.is_set(), seen) == (True, [built, later])


def test_a_circle_nobody_counts_for_a_seat_relays_nowhere() -> None:
    seen: list[IndexerClient] = []
    with WarmSeat.watching(seen.append):
        WarmSeat.relay(_round())
    assert (TAKEN.get(), seen) == (None, [])


@pytest.mark.machine
def test_the_viewer_who_takes_the_circle_over_gets_its_clients() -> None:
    """The adopted circle is counted without the viewer's hook: his verdict waited it out.

    Stand, silent Knaben: a taken «Terminator» answered 0.4-0.9 s after its circle, the
    untaken 0.1-0.2 s, as the poster verdict started only on the finished list.
    """
    done = threading.Event()
    HOST_SLOTS.sent("Knaben", done)  # the last search's silent Knaben request
    built, later = _round(), _round()
    entered = threading.Event()

    def circle(_query: str) -> list[Plan]:
        WarmSeat.relay(built)  # the viewer's text round is built before it stands in the queues
        entered.set()
        HOST_SLOTS.give_way(["Knaben"])
        WarmSeat.relay(later)
        return []

    hands = _Hands()
    cache = WarmCache(circle=circle, blurbs=lambda _p: None, spawn=hands)
    cache.ask(["x"])
    assert entered.wait(1.0)
    seen: list[IndexerClient] = []
    with WarmSeat.watching(seen.append):
        cache.take_live("x", circle=lambda _q: [])
    done.set()
    hands.join()
    assert seen == [built, later], "the viewer's hook missed the circle he took over"
