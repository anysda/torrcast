"""Checks that a name not gone when its circle ends is kept back and frees its host slot."""

from __future__ import annotations

import threading
from typing import Any

import pytest

from tests.adapters.prowlarr.test_circle_joint import _Asked
from tests.adapters.prowlarr.test_indexer_circle import _KNABEN, _RUTOR
from tests.adapters.prowlarr.test_spawn_ask import asleep
from torrcast.adapters.prowlarr import spawn_ask as spawn_ask_module
from torrcast.adapters.prowlarr.drop_unsent import drop_unsent
from torrcast.adapters.prowlarr.host_slots import PACE, HostSlots
from torrcast.adapters.prowlarr.indexer_circle import IndexerCircle
from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi
from torrcast.adapters.prowlarr.spawn_ask import _Ask


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_a_name_kept_back_under_another_slot_gives_it_back_all_the_same() -> None:
    """Two names kept back from under a later one held its request 4 s on an empty queue."""
    slots = HostSlots(_Clock())
    first, second, third = (slots.claim("Knaben", 9.0) for _ in range(3))
    assert first and second and third
    asked = [_Ask("Knaben", 3.0, slot=one.ticket) for one in (first, second)]
    assert drop_unsent(asked, slots) == ["Knaben", "Knaben"]
    assert slots.due("Knaben", third.ticket) == 0.0, "the third one moved up to the first slot"
    assert slots.claim("Knaben", 9.0) == (PACE, 100.0 + PACE, 4), "the next is drawn behind it"


@pytest.mark.parametrize("joint", ["", None])
def test_a_name_still_queued_when_its_circle_ends_is_never_sent(
    joint: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = threading.Event()  # the queued request's hold ends only when the test says so

    def hold(_seconds: float) -> None:
        gate.wait(2.0)

    asleep(monkeypatch, hold)
    http = _Asked()
    slots = HostSlots()
    circle = IndexerCircle(
        ProwlarrApi("http://p", "KEY", http=http), slack=0.05, budget_of=lambda _n: 3.0, slots=slots
    )
    slots.take("Knaben", 3.0)  # the search before drew Knaben's slot: this name queues behind
    drawn = slots._line._free["Knaben"]
    circle.run([_KNABEN, _RUTOR], "Cars 2006", 100, joint=joint)
    gate.set()
    sent: Any = [one for one in threading.enumerate() if one.name == "idx-Knaben"]
    for one in sent:
        one.join(2.0)
    if joint is None:
        assert 1 in http.texts, "the viewer's text is always sent"
        return
    assert 1 not in http.texts, "the name left after its circle had ended"
    assert slots._line._free["Knaben"] == drawn, "its slot went back to the next request"
    assert "Knaben" not in circle.lost and "Knaben" in circle.unheard(), "unsent, not silent"


@pytest.mark.machine
def test_a_search_waiting_on_anothers_request_hears_its_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TC-1404: the circle that sent a name ends first, the one that followed it still waits."""
    gate = threading.Event()
    asleep(monkeypatch, lambda _s: gate.wait(5.0))
    http = _Asked()
    api = ProwlarrApi("http://p", "KEY", http=http)
    slots = HostSlots(pace=1.2)
    first = IndexerCircle(api, slack=0.05, budget_of=lambda _n: 1.5, slots=slots)
    second = IndexerCircle(api, slack=0.05, budget_of=lambda _n: 3.0, slots=slots)
    slots.take("Knaben", 3.0)  # the name queues behind this slot and waits at the gate
    same: Any = {"args": ([_KNABEN], "Cars 2006", 100), "kwargs": {"joint": ""}}
    sender = threading.Thread(target=first.run, **same)
    sender.start()
    while not spawn_ask_module._FLYING and sender.is_alive():
        threading.Event().wait(0.005)
    follower = threading.Thread(target=second.run, **same)
    follower.start()
    sender.join(5.0)
    gate.set()
    follower.join(5.0)
    assert "Knaben" not in second.lost, "the follower is not told the indexer was silent"
    assert 1 in http.texts, "a request another search still waits for is sent"
    assert "Knaben" in second.answered
