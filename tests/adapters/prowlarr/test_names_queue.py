"""Checks that a picture's name stands in the shorter of the tracker's and its twin's queues."""

from __future__ import annotations

from tests.adapters.prowlarr.test_host_slots import _Clock
from torrcast.adapters.prowlarr.host_slots import HostSlots
from torrcast.adapters.prowlarr.names_queue import names_queue

_KNABEN = (1, "Knaben")
_RUTOR = (2, "RuTor")
_TWIN = (6, "RuTor names")


def test_an_idle_twin_takes_the_name() -> None:
    slots = HostSlots(_Clock())
    slots.take("RuTor", 3.0)  # the viewer's text is at RuTor
    assert names_queue(slots, [_KNABEN, _RUTOR, _TWIN]) == [_KNABEN, _TWIN]


def test_a_tie_goes_to_the_twin() -> None:
    assert names_queue(HostSlots(_Clock()), [_RUTOR, _TWIN]) == [_TWIN]


def test_the_name_goes_to_the_tracker_while_the_feed_holds_the_twin() -> None:
    clock = _Clock()
    slots = HostSlots(clock)
    slots.take("RuTor names", 15.0)  # the shelves' feed left with the search
    clock.now += 0.3
    slots.take("RuTor", 3.0)  # the viewer's text
    assert names_queue(slots, [_RUTOR, _TWIN]) == [_TWIN], "the twin is free 0.3 s sooner"
    slots.take("RuTor names", 3.0, spare=True)  # the first name
    assert names_queue(slots, [_RUTOR, _TWIN]) == [_RUTOR], "RuTor now starts 1.7 s sooner"


def test_a_lone_tracker_or_twin_is_asked_itself() -> None:
    slots = HostSlots(_Clock())
    assert names_queue(slots, [_KNABEN, _RUTOR]) == [_KNABEN, _RUTOR]
    assert names_queue(slots, [_KNABEN, _TWIN]) == [_KNABEN, _TWIN]
