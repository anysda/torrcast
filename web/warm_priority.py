"""Priority insertion for an open card's indexer circle."""

from __future__ import annotations

import contextlib
from typing import Any

from torrcast.domain.torrcast_error import TorrcastError


def _hint(cache: Any, query: str) -> int:
    """Schedule the card before background work without replacing that work."""
    query = query.strip()
    if not query or cache.ready(query) is not None:
        return 0
    with cache._cond:
        if query in cache._busy or query in cache._urgent:
            return 0
        cache._queue = [queued for queued in cache._queue if queued != query]
        cache._urgent.append(query)
        hands = max(0, min(cache.workers - cache._running, 1))
        cache._running += hands
    for _ in range(hands):
        cache.spawn(cache._pump)
    return 1


def _warm_blurbs(cache: Any, wanted: Any) -> None:
    with contextlib.suppress(TorrcastError, OSError):
        cache.blurbs(wanted)


__all__ = ["_hint", "_warm_blurbs"]
