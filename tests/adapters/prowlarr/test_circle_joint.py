"""Checks the circle of the picture's names: joined texts for JacRed, no quorum hold."""

from __future__ import annotations

import threading
import time
import urllib.parse
from typing import Any

import pytest

from tests.adapters.prowlarr.test_indexer_circle import _KNABEN, _RUTOR, _Http
from tests.adapters.prowlarr.test_prowlarr import _asked, _swarm, _swarm_of
from torrcast.adapters.prowlarr.indexer_circle import IndexerCircle
from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi
from torrcast.domain.joint_query import NAMES_BEHIND
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
    client.behind = 0.0
    began = time.monotonic()
    try:
        results = client.search("Cars 2006")
        elapsed = time.monotonic() - began
    finally:
        _swarm_of(client).gate.set()
        client.late(wait=5.0)
    assert len(results) == 2, "RuTor answered, Knaben is still on its way, Nyaa is not asked"
    assert elapsed < 0.5, f"the names waited {elapsed:.2f} s for the quorum"


@pytest.mark.machine
@pytest.mark.parametrize(("joint", "waits"), [(None, True), ("", False)])
def test_only_the_viewers_text_waits_for_a_late_one_on_an_empty_pool(
    joint: str | None, waits: bool
) -> None:
    client = _swarm(rows=2, empty={1, 2}, hold={3})  # Nyaa is on its way
    if joint is not None:
        client.beside(joint)
        client.behind = 0.0
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


@pytest.mark.parametrize(("joint", "behind"), [(None, False), ("", True)])
def test_the_names_leave_the_first_slot_to_the_viewers_text(
    joint: str | None, behind: bool
) -> None:
    client = _swarm(rows=2)
    if joint is not None:
        client.beside(joint)
    client._began = time.monotonic()
    client.search("Cars 2006")
    elapsed = time.monotonic() - client._began
    assert (elapsed >= NAMES_BEHIND) is behind, f"first circle done in {elapsed:.2f} s"


@pytest.mark.parametrize(("joint", "anime"), [(None, ["1", "2", "3"]), ("", ["1", "2"])])
def test_only_the_viewers_text_calls_the_anime_indexers_on_a_thin_pool(
    joint: str | None, anime: list[str]
) -> None:
    client = _swarm(rows=2, empty={1, 2, 3})
    if joint is not None:
        client.beside(joint)
        client.behind = 0.0
    with pytest.raises(NotFoundError):
        client.search("Cars 2006")
    assert _asked(client) == anime
