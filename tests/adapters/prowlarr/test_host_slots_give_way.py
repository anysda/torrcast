"""Checks that the viewer's search goes first in Prowlarr's queues and the warmup waits."""

from __future__ import annotations

import threading
import time

import pytest

from torrcast.adapters.prowlarr.host_slots import HostSlots
from torrcast.adapters.prowlarr.warmup import warmup


def _held(slots: HostSlots, names: list[str], most: float = 5.0) -> float:
    """Seconds a warmup circle to ``names`` was held before it could start."""
    with warmup():
        began = time.monotonic()
        return slots.give_way(names, most) - began


def test_a_viewers_circle_starts_at_once_whatever_the_queue() -> None:
    slots = HostSlots(pace=5.0)
    for _ in range(3):
        slots.take("YTS", 6.0)
    with slots.live():
        began = time.monotonic()
        assert slots.give_way(["YTS"]) - began < 0.05


@pytest.mark.machine
def test_a_warmup_starts_only_when_the_live_search_ends() -> None:
    slots = HostSlots()
    held: list[float] = []
    live = slots.live()
    live.__enter__()
    warm = threading.Thread(target=lambda: held.append(_held(slots, ["YTS"])))
    warm.start()
    time.sleep(0.3)
    assert not held, "the warmup went to the indexers while a viewer searched"
    live.__exit__(None, None, None)
    warm.join(2.0)
    assert held and 0.25 < held[0] < 1.0, held


@pytest.mark.machine
def test_a_warmup_waits_out_its_hosts_queue_and_only_theirs() -> None:
    slots = HostSlots(pace=0.4)
    slots.take("YTS", 6.0)
    slots.take("YTS", 6.0)
    assert _held(slots, ["RuTor"]) < 0.05, "another host has its own queue"
    assert 0.7 < _held(slots, ["YTS", "RuTor"]) < 1.2, "two slots of YTS were still ahead"


@pytest.mark.machine
def test_a_warmup_is_not_starved_by_live_searches_for_good() -> None:
    slots = HostSlots()
    with slots.live():
        assert 0.25 < _held(slots, ["YTS"], most=0.3) < 0.8


@pytest.mark.machine
def test_a_warmup_waits_for_the_request_still_in_flight_to_its_host() -> None:
    # Prowlarr runs YTS 2.5 s apart, not two: the drawn slot is free before the host is.
    slots = HostSlots(pace=0.0)
    done = threading.Event()
    slots.take("YTS", 6.0)
    slots.sent("YTS", done)
    threading.Timer(0.4, done.set).start()
    assert _held(slots, ["RuTor"]) < 0.05, "another host's request does not hold it"
    assert 0.3 < _held(slots, ["YTS"]) < 1.0, "the warmup queued behind a request in flight"
