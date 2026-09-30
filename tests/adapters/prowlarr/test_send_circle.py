"""Checks how one circle is sent: whose text, what budget, who is left unsent."""

from __future__ import annotations

from typing import Any

from tests.adapters.prowlarr.test_host_slots import _Clock
from tests.adapters.prowlarr.test_indexer_circle import _KNABEN, _RUTOR, _Http
from torrcast.adapters.prowlarr.host_slots import HostSlots
from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi
from torrcast.adapters.prowlarr.send_circle import send_circle
from torrcast.adapters.prowlarr.spawn_ask import _Ask

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


class _Counted(_Http):
    """Knaben answers after a pause, and every request to it is counted."""

    def __init__(self) -> None:
        super().__init__(delay={1: 0.3})
        self.knaben = 0

    def get_json(self, session: Any, url: str, timeout: float, base_url: str) -> Any:
        self.knaben += url.endswith("&indexerIds=1")
        return super().get_json(session, url, timeout, base_url)


def test_a_text_on_its_way_is_not_sent_again_but_waited() -> None:
    """Two circles of one search sent Knaben one text, and the second stood behind the first."""
    http, slots = _Counted(), HostSlots(_Clock())
    api = ProwlarrApi("http://p", "KEY", http=http)

    def ask() -> tuple[list[_Ask], object]:
        return send_circle(
            api, slots, [_KNABEN], "Cars", 100, None, budgets=_BUDGETS.__getitem__, cap=0.0
        )

    (first,), _ = ask()
    (second,), _ = ask()
    assert second.done.wait(2.0) and first.done.is_set()
    assert http.knaben == 1, "the second circle waits the request already on its way"
    assert second.rows == first.rows and second.rows, "and gets its rows"
    assert second.judge is first.judge, "one request tells the book one outcome"
    (third,), _ = ask()
    assert third.done.wait(2.0) and http.knaben == 2, "an ended request is asked anew"


def test_a_name_in_the_host_s_queue_gets_its_budget_past_its_slot() -> None:
    """RuTor's names left Prowlarr at +2.1 s: a 3 s budget from the send lost their rows."""
    http, slots = _Http(), HostSlots(_Clock())
    slots.take("RuTor", 3.0)
    api = ProwlarrApi("http://p", "KEY", http=http)
    (rutor,), unsent = send_circle(
        api, slots, [_RUTOR], "Cars", 100, "", budgets=_BUDGETS.__getitem__, cap=0.0
    )
    assert rutor.done.wait(1.0) and unsent == []
    assert rutor.budget == 3.0 + 2.0, "the circle waits it from its slot"
    assert http.budget[2] == 3.0 + 2.0, "and the request lives that long"
