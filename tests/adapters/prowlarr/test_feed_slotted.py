"""Checks that the shelves' feed draws its slots: the names see the twin's queue it holds."""

from __future__ import annotations

import pytest

from tests.adapters.prowlarr.test_host_slots import _Clock
from tests.adapters.prowlarr.test_indexer_circle import _Http
from torrcast.adapters.prowlarr import feed_slotted as feed_slotted_module
from torrcast.adapters.prowlarr.feed_slotted import feed_slotted
from torrcast.adapters.prowlarr.host_slots import PACE, HostSlots
from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi

_PAIRS = [(1, "Knaben"), (2, "RuTor"), (6, "RuTor names")]


def test_each_feed_request_draws_its_hosts_slot() -> None:
    slots = HostSlots(_Clock())
    http = _Http()
    feed_slotted(ProwlarrApi("http://p", "KEY", http=http), slots, _PAIRS, 50, 1.0)
    assert sorted(http.budget) == [1, 6], "RuTor once, through its twin"
    assert slots.starts("RuTor names") == 100.0 + PACE, "the twin holds the feed"
    assert slots.starts("Knaben") == 100.0 + PACE
    assert slots.starts("RuTor") == 100.0, "RuTor itself is left to the viewer"


def test_a_feed_request_is_in_flight_till_it_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    slots = HostSlots(_Clock())
    flying: list[bool] = []
    api = ProwlarrApi("http://p", "KEY", http=_Http())
    real = api.get_json

    def get(url: str, timeout: float | None = None) -> object:
        flying.append(any(not one.is_set() for one in slots._flight["RuTor names"]))
        return real(url, timeout)

    monkeypatch.setattr(api, "get_json", get)
    feed_slotted(api, slots, _PAIRS[1:], 50, 1.0)
    assert flying == [True]
    assert all(one.is_set() for one in slots._flight["RuTor names"])
    assert feed_slotted_module.__all__ == ["feed_slotted"]
