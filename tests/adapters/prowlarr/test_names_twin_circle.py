"""Checks that the picture's names go to RuTor's twin, past the queue of the viewer's text."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.adapters.prowlarr.test_host_slots import _Clock
from tests.adapters.prowlarr.test_indexer_circle import _KNABEN, _RUTOR, _Http
from tests.adapters.prowlarr.test_spawn_ask import asleep
from torrcast.adapters.prowlarr import feed_slotted as feed_slotted_module
from torrcast.adapters.prowlarr.from_json import from_json
from torrcast.adapters.prowlarr.host_slots import HostSlots
from torrcast.adapters.prowlarr.prowlarr import Prowlarr
from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi
from torrcast.adapters.prowlarr.send_circle import send_circle

_TWIN = (6, "RuTor names")


def _sent(slots: HostSlots, joint: str | None, twin: bool = True) -> list[str]:
    api = ProwlarrApi("http://p", "KEY", http=_Http())
    asked, unsent = send_circle(
        api,
        slots,
        [_KNABEN, _RUTOR, _TWIN] if twin else [_KNABEN, _RUTOR],
        "Cars",
        100,
        joint=joint,
        budgets=lambda _n: 3.0,
        cap=4.0,
    )
    for ask in asked:
        ask.done.wait(1.0)
    assert unsent == []
    return [ask.name for ask in asked]


def test_the_names_skip_the_queue_the_viewers_text_stands_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    holds = asleep(monkeypatch)
    slots = HostSlots(_Clock())
    slots.take("RuTor", 3.0)  # the viewer's text is at RuTor
    assert _sent(slots, "") == ["Knaben", "RuTor names"]
    assert holds == [], "the name left at once: the twin is a queue of its own"


def test_the_next_searchs_text_never_stands_behind_a_name(monkeypatch: pytest.MonkeyPatch) -> None:
    asleep(monkeypatch)
    clock = _Clock()
    slots = HostSlots(clock)
    assert _sent(slots, None) == ["Knaben", "RuTor"]  # the viewer's text, RuTor till +2.0
    clock.now += 0.5
    slots.take("RuTor names", 15.0)  # the twin is taken till +2.5, later than RuTor
    assert _sent(slots, "") == ["Knaben", "RuTor names"], "the name waits at the twin"
    clock.now += 0.5  # the next search, a second after the first
    slot = slots.claim("RuTor", 3.0)
    assert slot is not None
    assert slot[0] == 1.0, "behind its own last text only, not 3.0 behind a name"


def test_without_the_twin_the_names_ask_rutor_as_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asleep(monkeypatch)
    assert _sent(HostSlots(_Clock()), "", twin=False) == ["Knaben", "RuTor"]


def test_the_viewers_text_never_asks_the_twin(monkeypatch: pytest.MonkeyPatch) -> None:
    asleep(monkeypatch)
    assert _sent(HostSlots(_Clock()), None) == ["Knaben", "RuTor"]


def test_the_twins_rows_are_rutors() -> None:
    row = {"title": "Тачки 2006", "infoHash": "a" * 40, "size": 1, "seeders": 5}
    (found,) = from_json([{**row, "indexer": "RuTor names"}])
    assert found.indexer == "RuTor"


def test_the_shelves_feed_asks_rutor_not_the_names_twin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []
    monkeypatch.setattr(
        feed_slotted_module, "feed_apart", lambda _get, urls, _within: asked.extend(urls)
    )
    client = Prowlarr("http://p/", "KEY")
    pairs = [_KNABEN, _RUTOR, _TWIN]
    roster = SimpleNamespace(known=lambda: pairs, usable=lambda known: (list(known), ()))
    monkeypatch.setattr(client, "_roster", roster)
    monkeypatch.setattr(client._api, "open", lambda: None)
    client.feed(50, within=1.0)
    assert [url.rsplit("&indexerIds=", 1)[1] for url in asked] == ["1", "2"], (
        "RuTor once, past the names' twin"
    )
