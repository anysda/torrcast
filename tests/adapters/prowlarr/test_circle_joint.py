"""Checks the circle of the picture's names: joined texts for JacRed, no quorum hold."""

from __future__ import annotations

import threading
import time
import urllib.parse
from typing import Any

import pytest

from tests.adapters.prowlarr.test_indexer_circle import _KNABEN, _RUTOR, _Http
from tests.adapters.prowlarr.test_prowlarr import _asked, _swarm, _swarm_of
from torrcast.adapters.prowlarr.host_slots import HOST_SLOTS
from torrcast.adapters.prowlarr.indexer_circle import IndexerCircle
from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi
from torrcast.domain.not_found_error import NotFoundError

_JACRED = (4, "JacRed")
_JOINT = "Тачки 2006 | Cars 2006"


class _Asked(_Http):
    """Remembers the text every indexer was asked."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.texts: dict[int, str] = {}

    def get_json(self, session: Any, url: str, timeout: float, base_url: str) -> Any:
        num = int(url.rsplit("&indexerIds=", 1)[1])
        self.texts[num] = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["query"][0]
        return super().get_json(session, url, timeout, base_url)


def _circle(**kwargs: Any) -> tuple[IndexerCircle, _Asked]:
    http = _Asked(**kwargs)
    api = ProwlarrApi("http://p", "KEY", http=http)
    return IndexerCircle(api, slack=0.05, budget_of=lambda name: 0.5), http


def test_jacred_gets_the_joined_names_and_the_rest_their_own_text() -> None:
    circle, http = _circle()
    circle.run([_KNABEN, _JACRED, _RUTOR], "Тачки 2006", 100, joint=_JOINT)
    assert http.texts == {1: "Тачки 2006", 2: "Тачки 2006", 4: _JOINT}


def test_an_empty_joint_leaves_jacred_to_the_client_that_carries_it() -> None:
    circle, http = _circle()
    circle.run([_KNABEN, _JACRED, _RUTOR], "Cars 2006", 100, joint="")
    assert http.texts == {1: "Cars 2006", 2: "Cars 2006"}
    assert "JacRed" not in circle.counts


def test_the_viewers_text_asks_jacred_as_before() -> None:
    circle, http = _circle()
    circle.run([_KNABEN, _JACRED], "Тачки", 100)
    assert http.texts == {1: "Тачки", 4: "Тачки"}


@pytest.mark.machine
@pytest.mark.parametrize(("joint", "held"), [(_JOINT, False), (None, True)])
def test_the_quorum_holds_the_viewers_text_but_not_the_names(joint: str | None, held: bool) -> None:
    circle, _http = _circle(delay={1: 0.9})
    began = time.monotonic()
    got, _error = circle.run([_KNABEN, _RUTOR], "Тачки 2006", 100, joint=joint)
    elapsed = time.monotonic() - began
    assert (elapsed > 0.5) is held, f"circle took {elapsed:.2f} s"
    assert len(got) == 1, "RuTor answered, Knaben is still on its way"
    assert len(circle.late(wait=2.0)) == 1, "the quorum's late rows still land in the top-up"


@pytest.mark.machine
def test_a_client_of_the_names_is_not_held_by_the_quorum() -> None:
    client = _swarm(hold={1}, rows=2)  # Knaben is held until the gate
    client.beside("")
    began = time.monotonic()
    try:
        results = client.search("Cars 2006")
        elapsed = time.monotonic() - began
    finally:
        _swarm_of(client).gate.set()
        client.late(wait=5.0)
    assert len(results) == 4, "RuTor and Nyaa answered, Knaben is still on its way"
    assert elapsed < 0.5, f"the names waited {elapsed:.2f} s for the quorum"


@pytest.mark.machine
@pytest.mark.parametrize(("joint", "waits"), [(None, True), ("", False)])
def test_only_the_viewers_text_waits_for_a_late_one_on_an_empty_pool(
    joint: str | None, waits: bool
) -> None:
    client = _swarm(rows=2, empty={1, 2}, hold={3})  # Nyaa is on its way
    if joint is not None:
        client.beside(joint)
    threading.Timer(0.6, _swarm_of(client).gate.set).start()
    began = time.monotonic()
    try:
        client.search("Naruto [TV]")
    except NotFoundError:
        assert not waits, "the viewer's text waited for the late rows"
    else:
        assert waits, "a client of the names waited for the late rows"
    elapsed = time.monotonic() - began
    assert (elapsed > 0.5) is waits, f"the pool stayed empty for {elapsed:.2f} s"
    client.late(wait=2.0)


@pytest.mark.machine
def test_the_names_leave_once_the_viewers_text_drew_its_slots_not_when_it_ends() -> None:
    client = _swarm(hold={1}, rows=2)  # Knaben holds the viewer's circle until the gate
    search = threading.Thread(target=client.search, args=("Cars 2006",), daemon=True)
    search.start()
    try:
        assert client.sent(1.0), "the names still wait while the viewer's text is out"
        assert search.is_alive(), "the event came from the end of the search, not its circle"
    finally:
        _swarm_of(client).gate.set()
        search.join(5.0)
        client.late(wait=5.0)


@pytest.mark.parametrize(
    ("query", "asked"), [("Cars 2006", ["1", "2", "3"]), ("Тачки 2006", ["1", "2"])]
)
def test_a_latin_name_asks_the_anime_indexers_at_once(query: str, asked: list[str]) -> None:
    client = _swarm(rows=2, empty={1, 2, 3})
    client.beside("")
    with pytest.raises(NotFoundError):
        client.search(query)
    assert _asked(client) == asked, "a Cyrillic name leaves Nyaa to the viewer's text"


@pytest.mark.parametrize(("joint", "asked"), [(None, {1, 2}), ("", {1})])
def test_a_name_behind_a_full_queue_is_not_sent(joint: str | None, asked: set[int]) -> None:
    circle, http = _circle()
    circle.slots.take("RuTor", 0.5)  # the slot the search before drew is still ahead
    circle.run([_KNABEN, _RUTOR], "Cars 2006", 100, joint=joint)
    assert set(http.texts) == asked
    assert "RuTor" not in circle.lost, "an unsent name is not a silent one"


@pytest.mark.machine
def test_the_rest_keeps_the_time_the_unsent_name_held_the_circle() -> None:
    circle, _http = _circle(delay={3: 0.2})  # Nyaa answers in 0.2 s, its budget is 0.5
    circle.slots.take("RuTor", 0.5)
    began = time.monotonic()
    got, _error = circle.run([_RUTOR, (3, "Nyaa.si")], "Cars 2006", 100, joint="")
    elapsed = time.monotonic() - began
    assert len(got) == 1, "the answer that came in the unsent name's time is kept"
    assert elapsed < 0.45, f"waited {elapsed:.2f} s, the unsent name held the circle 0.5 s"


@pytest.mark.machine
def test_an_unsent_name_does_not_leave_the_circle_waiting_the_rest_in_full() -> None:
    http = _Asked(delay={3: 0.6})
    budgets = {"RuTor": 0.2, "Nyaa.si": 1.0}
    circle = IndexerCircle(ProwlarrApi("http://p", "KEY", http=http), budget_of=budgets.__getitem__)
    circle.slots.take("RuTor", 0.2)
    began = time.monotonic()
    got, _error = circle.run([_RUTOR, (3, "Nyaa.si")], "Cars 2006", 100, joint="")
    elapsed = time.monotonic() - began
    assert elapsed < 0.5, f"the names waited {elapsed:.2f} s for one that only adds rows"
    assert got == [] and circle.waiting() == ("Nyaa.si",), "it comes late, not lost"
    circle.late(wait=2.0)


@pytest.mark.parametrize(("queued", "whole"), [(False, True), (True, False)])
def test_a_name_left_unsent_keeps_the_search_from_being_whole(queued: bool, whole: bool) -> None:
    client = _swarm(rows=5)
    client.beside("")
    for _ in range(3 if queued else 0):
        HOST_SLOTS.take("RuTor", 3.0)  # the searches before drew these slots
    client.search("Cars 2006")
    assert client._circle.unheard() == (("RuTor",) if queued else ())
    assert client.whole() is whole, "nobody heard RuTor, so nothing proves the catalogue"


@pytest.mark.machine
def test_a_silent_anime_indexer_does_not_hold_the_names() -> None:
    client = _swarm(rows=5, delay={3: 1.0})  # Nyaa is silent past the names' core
    client.beside("")
    began = time.monotonic()
    client.search("Cars 2006")
    elapsed = time.monotonic() - began
    assert elapsed < 0.5, f"the names waited {elapsed:.2f} s for Nyaa"
    assert client.waiting() == ("Nyaa.si",), "Nyaa was asked at once and comes late"
    client.late(wait=2.0)
