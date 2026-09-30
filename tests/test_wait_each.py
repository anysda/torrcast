"""Mirror for :mod:`hass.wait_each`: one deadline for the whole list, not one per name."""

from __future__ import annotations

import threading
import time

import pytest

from hass.wait_each import wait_each


@pytest.mark.machine
def test_the_limit_covers_all_names_together() -> None:
    """Rollback (a fresh limit per name): three silent claims hold the caller three times over."""
    events = {name: threading.Event() for name in ("a", "b", "c")}
    began = time.monotonic()
    wait_each(threading.Lock(), events, ["a", "b", "c"], 0.2)
    assert time.monotonic() - began < 0.4


@pytest.mark.machine
def test_a_set_or_missing_name_does_not_hold_the_caller() -> None:
    done = threading.Event()
    done.set()
    began = time.monotonic()
    wait_each(threading.Lock(), {"done": done}, ["gone", "done"], 5.0)
    assert time.monotonic() - began < 0.5


@pytest.mark.machine
def test_the_caller_wakes_when_the_claim_is_released() -> None:
    event = threading.Event()
    threading.Timer(0.1, event.set).start()
    began = time.monotonic()
    wait_each(threading.Lock(), {"a": event}, ["a"], 5.0)
    assert 0.05 < time.monotonic() - began < 1.0
