"""Completion signal for a fact flight."""

from __future__ import annotations

import threading


def settled(about: threading.Event, done: threading.Event) -> None:
    """Release both waiters when a fact source has no more work to offer."""
    about.set()
    done.set()


__all__ = ["settled"]
