"""Checks the picture of Prowlarr's pacing queue the process keeps across searches."""

from __future__ import annotations

from torrcast.adapters.prowlarr.host_slots import HOST_SLOTS, PACE, HostSlots
from torrcast.adapters.prowlarr.indexer_circle import IndexerCircle
from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_the_viewers_text_is_sent_however_long_the_queue() -> None:
    slots = HostSlots(_Clock())
    assert all(slots.take("RuTor", 3.0) for _ in range(4))
    assert slots._free["RuTor"] == 100.0 + 4 * PACE


def test_a_name_that_cannot_start_in_its_budget_is_not_sent() -> None:
    slots = HostSlots(_Clock())
    assert slots.take("RuTor", 3.0)
    assert slots.take("RuTor", 3.0, spare=True), "the second slot starts in two seconds"
    assert not slots.take("RuTor", 3.0, spare=True), "the third starts at the budget"
    assert slots.take("YTS", 3.0, spare=True), "another host has its own queue"
    assert slots._free["RuTor"] == 100.0 + 2 * PACE, "the unsent name drew no slot"


def test_the_queue_empties_with_time() -> None:
    clock = _Clock()
    slots = HostSlots(clock)
    for _ in range(3):
        slots.take("RuTor", 3.0)
    assert not slots.take("RuTor", 3.0, spare=True)
    clock.now += 3 * PACE
    assert slots.take("RuTor", 3.0, spare=True)


def test_the_process_keeps_one_queue() -> None:
    first, second = (IndexerCircle(ProwlarrApi("http://p", "KEY")) for _ in range(2))
    for _ in range(2):
        first.slots.take("RuTor", 3.0)
    assert not second.slots.take("RuTor", 3.0, spare=True), "a new search sees the old queue"
    assert "RuTor" in HOST_SLOTS._free


def test_the_shelf_waits_only_behind_a_viewers_search() -> None:
    clock = _Clock()
    slots = HostSlots(clock)
    assert slots.after_search(100.0) == 0.0, "the start of the process does not hold the shelf"
    with slots.live():
        clock.now += 70.0
        assert slots.after_search(100.0) == -10.0, "a search does not hold it past 60 s"
        assert slots.after_search(170.0) == 60.0
    assert slots.after_search(170.0) == 15.0, "the quiet after a search is 15 s"
    assert slots.after_search(100.0) == -10.0, "nor does the quiet hold it past 60 s"
    clock.now += 15.0
    assert slots.after_search(170.0) == 0.0


def test_a_warmup_holds_off_fifteen_seconds_past_the_start_and_every_search() -> None:
    clock = _Clock()
    slots = HostSlots(clock)

    def sleep(seconds: float) -> None:
        clock.now += seconds
        if clock.now == 110.0:
            with slots.live():  # a search ends ten seconds into the wait
                pass

    slots.hold_off(sleep)
    assert clock.now == 125.0, "15 s after the search that ended at 110"
    clock.now = 200.0
    with slots.live():
        slots.hold_off(lambda seconds: setattr(clock, "now", clock.now + seconds))
    assert clock.now == 260.0, "a search that never ends holds it 60 s at the longest"
