"""Checks how one circle is sent: whose text, what budget, who is left unsent."""

from __future__ import annotations

from tests.adapters.prowlarr.test_host_slots import _Clock
from tests.adapters.prowlarr.test_indexer_circle import _KNABEN, _RUTOR, _Http
from torrcast.adapters.prowlarr.host_slots import HostSlots
from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi
from torrcast.adapters.prowlarr.send_circle import send_circle

_JACRED = (4, "JacRed")
_BUDGETS = {"Knaben": 6.0, "RuTor": 3.0, "JacRed": 5.0}


def _sent(slots: HostSlots, joint: str | None, cap: float = 0.0) -> tuple[list[str], object]:
    api = ProwlarrApi("http://p", "KEY", http=_Http())
    pairs = [_KNABEN, _RUTOR, _JACRED]
    asked, unsent = send_circle(
        api, slots, pairs, "Cars", 100, joint=joint, budgets=_BUDGETS.__getitem__, cap=cap
    )
    for ask in asked:
        ask.done.wait(1.0)
    return [ask.name for ask in asked], unsent


def test_the_cap_cuts_every_budget_and_the_viewers_text_is_always_sent() -> None:
    slots = HostSlots(_Clock())
    slots.take("RuTor", 3.0)
    slots.take("RuTor", 3.0)
    names, unsent = _sent(slots, None, cap=4.0)
    assert names == ["Knaben", "RuTor", "JacRed"] and unsent == []
    assert slots._free["RuTor"] == 100.0 + 6.0, "the viewer's text drew the third slot"


def test_a_name_behind_the_queue_comes_back_unsent_with_its_budget() -> None:
    slots = HostSlots(_Clock())
    slots.take("RuTor", 3.0)
    slots.take("RuTor", 3.0)
    names, unsent = _sent(slots, "", cap=4.0)
    assert names == ["Knaben"], "RuTor waits behind the queue, JacRed is carried by another client"
    assert unsent == [("RuTor", 3.0)]


def test_every_sent_request_is_in_flight_at_its_host_until_it_ends() -> None:
    slots = HostSlots(_Clock())
    _sent(slots, None)
    assert sorted(slots._flight) == ["JacRed", "Knaben", "RuTor"], "a warmup could not see them"
    assert all(one.is_set() for flying in slots._flight.values() for one in flying)
