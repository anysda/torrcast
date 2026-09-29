"""Checks how long a circle waits, and for whom, when its core was left unsent."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from torrcast.adapters.prowlarr.circle_wait import circle_wait
from torrcast.adapters.prowlarr.spawn_ask import _Ask


def _waited(asked: list[_Ask], **kwargs: Any) -> tuple[list[_Ask], float]:
    began = time.monotonic()
    core = circle_wait(asked, names=True, began=began, slack=0.0, **kwargs)
    return core, time.monotonic() - began


@pytest.mark.machine
def test_a_circle_without_a_core_waits_every_one() -> None:
    yts = _Ask("YTS", 0.3)
    core, elapsed = _waited([yts])
    assert core == [yts]
    assert elapsed >= 0.3, f"waited {elapsed:.2f} s for the only one asked"


@pytest.mark.machine
def test_an_unsent_core_holds_the_rest_its_budget_and_no_longer() -> None:
    yts = _Ask("YTS", 5.0)
    core, elapsed = _waited([yts], unsent=[("RuTor", 0.2)])
    assert core == [], "the one left is not the core: it comes late"
    assert 0.2 <= elapsed < 1.0, f"waited {elapsed:.2f} s instead of the unsent budget"


@pytest.mark.machine
def test_the_rest_that_answers_within_the_hold_ends_it() -> None:
    yts = _Ask("YTS", 5.0)
    threading.Timer(0.1, yts.done.set).start()
    _core, elapsed = _waited([yts], unsent=[("RuTor", 0.2)])
    assert yts.done.is_set()
    assert elapsed < 0.2, f"waited {elapsed:.2f} s after the last answer"


@pytest.mark.machine
def test_an_unsent_quorum_does_not_hold_a_circle_of_names() -> None:
    rutor, yts = _Ask("RuTor", 5.0), _Ask("YTS", 5.0)
    threading.Timer(0.1, rutor.done.set).start()
    core, elapsed = _waited([rutor, yts], unsent=[("Knaben", 0.5)])
    assert core == [rutor] and not yts.done.is_set(), "YTS only adds rows: it comes late"
    assert elapsed < 0.4, f"waited {elapsed:.2f} s for a quorum the names never wait"


def test_the_quorum_holds_only_the_viewers_text() -> None:
    knaben, rutor = _Ask("Knaben", 0.1), _Ask("RuTor", 0.1)
    assert circle_wait([knaben, rutor], names=True, began=0.0, slack=0.0) == [rutor]
    assert circle_wait([knaben, rutor], names=False, began=0.0, slack=0.0) == [knaben, rutor]
