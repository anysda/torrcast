"""Checks that an empty circle waits the late ones only while the search has found nothing."""

from __future__ import annotations

import time

import pytest

from tests.adapters.prowlarr.test_prowlarr import _swarm, _swarm_of
from torrcast.adapters.prowlarr.circle_wait import QUORUM_GRACE
from torrcast.domain.not_found_error import NotFoundError


def test_an_empty_later_circle_does_not_wait_the_late_once_rows_were_found() -> None:
    """TC-318 waits for a search with nothing to show; the second-language circle has some."""
    client = _swarm(rows=2, empty={1, 2}, hold={3})
    _swarm_of(client).gate.set()
    assert client.search("Naruto [TV]"), "the first circle brought Nyaa's rows"
    _swarm_of(client).gate.clear()
    client._began = time.monotonic() - 4.0  # six seconds of the goal are left
    began = time.monotonic()
    try:
        with pytest.raises(NotFoundError):
            client.search("Naruto [TV] 2002")
    finally:
        _swarm_of(client).gate.set()
    # The quorum grace is waited either way; the rest of the goal is not.
    held = time.monotonic() - began
    assert held < QUORUM_GRACE + 1.5, "the late one held the empty circle to the goal"


def test_an_empty_first_circle_still_waits_the_late_one() -> None:
    client = _swarm(rows=2, empty={1, 2}, hold={3})
    assert client.late_wait() > 9.0, "nothing found yet: the rest of the goal is waited"
