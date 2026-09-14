"""Checks fact-flight completion signalling."""

from __future__ import annotations

import threading

from torrcast.usecases.settled import settled


def test_settled_releases_both_fact_waiters() -> None:
    """A finished source cannot leave either kind of fact wait behind."""
    about, done = threading.Event(), threading.Event()

    settled(about, done)

    assert about.is_set() and done.is_set()
