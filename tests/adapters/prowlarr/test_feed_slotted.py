"""Checks that the shelves' feed draws its slots at RuTor itself: the twin is the names'."""

from __future__ import annotations

import pytest

from tests.adapters.prowlarr.test_host_slots import _Clock
from tests.adapters.prowlarr.test_indexer_circle import _Http
from torrcast.adapters.prowlarr import feed_slotted as feed_slotted_module
from torrcast.adapters.prowlarr.feed_slotted import feed_slotted
from torrcast.adapters.prowlarr.host_slots import PACE, HostSlots
from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi

_PAIRS = [(1, "Knaben"), (2, "RuTor"), (6, "RuTor names")]


def _queued(slots: HostSlots, name: str) -> float:
    slot = slots.claim(name, 9.0)
    assert slot is not None
    return slot[0]


def test_each_feed_request_draws_its_hosts_slot() -> None:
    slots = HostSlots(_Clock())
    http = _Http()
    feed_slotted(ProwlarrApi("http://p", "KEY", http=http), slots, _PAIRS, 50, 1.0)
    assert sorted(http.budget) == [1, 2], "RuTor once, at RuTor itself"
    assert _queued(slots, "RuTor") == PACE, "the viewer's text counts its budget past the feed"
    assert _queued(slots, "Knaben") == PACE
    assert _queued(slots, "RuTor names") == 0.0, "the twin is left to the picture's names"


def test_a_feed_request_is_in_flight_till_it_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    slots = HostSlots(_Clock())
    flying: list[bool] = []
    api = ProwlarrApi("http://p", "KEY", http=_Http())
    real = api.get_json

    def get(url: str, timeout: float | None = None) -> object:
        flying.append(any(not one.is_set() for one in slots._flight["RuTor"]))
        return real(url, timeout)

    monkeypatch.setattr(api, "get_json", get)
    feed_slotted(api, slots, _PAIRS[1:], 50, 1.0)
    assert flying == [True]
    assert all(one.is_set() for one in slots._flight["RuTor"])
    assert feed_slotted_module.__all__ == ["feed_slotted"]
