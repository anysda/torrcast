"""The one background hand of :class:`web.warm_cache.WarmCache`: queue, urgent card, refresh."""

from __future__ import annotations

from typing import Any

from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.torrcast_error import TorrcastError
from web.warm_priority import _hint


def _pump(cache: Any) -> None:
    """Take from the queue until it ends, giving way to a live request.

    A screen is warmed from disk offline. A card (the urgent queue) woke a circle from disk,
    and the show plays only a circle from the network, so that one is refreshed right behind.
    """
    try:
        while True:
            cache._quiet()
            with cache._cond:
                if not cache._urgent and not cache._queue:
                    return
                urgent = bool(cache._urgent)
                query = cache._urgent.pop(0) if urgent else cache._queue.pop(0)
                if query in cache._busy or (
                    cache.ready(query) is not None and query not in cache._stale
                ):
                    continue  # a live caller already runs or landed this very circle
                cache._busy.add(query)
                stale = query in cache._stale
                cache._stale.discard(query)
            kept = None
            try:
                kept = None if stale else cache._memory.revive(query)
                plans = cache.circle(query) if kept is None else kept
            except NotFoundError as nothing:
                cache._memory.refuse(query, nothing)
                plans = []
            except (TorrcastError, OSError):
                plans = []
            cache._remember(query, plans, revived=kept is not None)
            with cache._cond:
                cache._busy.discard(query)
                cache._cond.notify_all()
            if kept is not None and urgent:
                _hint(cache, query, stale=True)
    finally:
        with cache._cond:
            cache._running -= 1


__all__ = ["_pump"]
