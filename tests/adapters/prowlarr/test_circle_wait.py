"""Checks how long a circle waits, and for whom, when its core was left unsent."""

from __future__ import annotations

import threading
import time

import pytest

from torrcast.adapters.prowlarr.circle_wait import circle_wait
from torrcast.adapters.prowlarr.spawn_ask import _Ask

pytestmark = pytest.mark.machine


def _waited(asked: list[_Ask], **kwargs: float) -> tuple[list[_Ask], float]:
    began = time.monotonic()
    core = circle_wait(asked, names=True, began=began, slack=0.0, **kwargs)
    return core, time.monotonic() - began


def test_a_circle_without_a_core_waits_every_one() -> None:
    yts = _Ask("YTS", 0.3)
    core, elapsed = _waited([yts])
    assert core == [yts]
    assert elapsed >= 0.3, f"waited {elapsed:.2f} s for the only one asked"


def test_an_unsent_core_holds_the_rest_its_budget_and_no_longer() -> None:
    yts = _Ask("YTS", 5.0)
    core, elapsed = _waited([yts], held=0.2)
    assert core == [], "the one left is not the core: it comes late"
    assert 0.2 <= elapsed < 1.0, f"waited {elapsed:.2f} s instead of the unsent budget"


def test_the_rest_that_answers_within_the_hold_ends_it() -> None:
    yts = _Ask("YTS", 5.0)
    threading.Timer(0.1, yts.done.set).start()
    _core, elapsed = _waited([yts], held=0.2)
    assert yts.done.is_set()
    assert elapsed < 0.2, f"waited {elapsed:.2f} s after the last answer"


def test_the_quorum_holds_only_the_viewers_text() -> None:
    knaben, rutor = _Ask("Knaben", 0.1), _Ask("RuTor", 0.1)
    assert circle_wait([knaben, rutor], names=True, began=0.0, slack=0.0) == [rutor]
    assert circle_wait([knaben, rutor], names=False, began=0.0, slack=0.0) == [knaben, rutor]
