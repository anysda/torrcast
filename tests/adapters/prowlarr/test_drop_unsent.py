"""Checks that a name not gone when its circle ends is kept back and frees its host slot."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any

import pytest

from tests.adapters.prowlarr.test_circle_joint import _Asked
from tests.adapters.prowlarr.test_indexer_circle import _KNABEN, _RUTOR
from torrcast.adapters.prowlarr import spawn_ask as spawn_ask_module
from torrcast.adapters.prowlarr.host_slots import PACE, HostSlots
from torrcast.adapters.prowlarr.indexer_circle import IndexerCircle
from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_only_the_hosts_last_slot_comes_back() -> None:
    slots = HostSlots(_Clock())
    first = slots.claim("Knaben", 9.0)
    second = slots.claim("Knaben", 9.0)
    assert first == (0.0, 100.0) and second == (PACE, 100.0 + PACE)
    slots.give_back("Knaben", 100.0)
    assert slots._free["Knaben"] == 100.0 + 2 * PACE, "a slot under another one stays drawn"
    slots.give_back("Knaben", 100.0 + PACE)
    assert slots._free["Knaben"] == 100.0 + PACE, "the last one is free for the next request"


@pytest.mark.parametrize("joint", ["", None])
def test_a_name_still_queued_when_its_circle_ends_is_never_sent(
    joint: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = threading.Event()  # the queued request's hold ends only when the test says so

    def hold(_seconds: float) -> None:
        gate.wait(2.0)

    monkeypatch.setattr(spawn_ask_module, "time", SimpleNamespace(sleep=hold))
    http = _Asked()
    slots = HostSlots()
    circle = IndexerCircle(
        ProwlarrApi("http://p", "KEY", http=http), slack=0.05, budget_of=lambda _n: 3.0, slots=slots
    )
    slots.take("Knaben", 3.0)  # the search before drew Knaben's slot: this name queues behind
    drawn = slots._free["Knaben"]
    circle.run([_KNABEN, _RUTOR], "Cars 2006", 100, joint=joint)
    gate.set()
    sent: Any = [one for one in threading.enumerate() if one.name == "idx-Knaben"]
    for one in sent:
        one.join(2.0)
    if joint is None:
        assert 1 in http.texts, "the viewer's text is always sent"
        return
    assert 1 not in http.texts, "the name left after its circle had ended"
    assert slots._free["Knaben"] == drawn, "its slot went back to the next request"
    assert "Knaben" not in circle.lost and "Knaben" in circle.unheard(), "unsent, not silent"
