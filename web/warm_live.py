"""Circle for the show: only one that came from the network, never a record from disk.

A circle from disk stood for hours: releases left the pool, seeders went stale, a source that
was silent then is missing, and the Rick and Morty episode row did not start on it in four runs.
The card may show such a circle at once; the show waits for the refresh or counts its own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def _landed(cache: Any, query: str, patience: float) -> list[Plan] | None:
    """A live circle, waiting for the one that runs; ``None`` - none runs, count your own."""
    key = query.strip()
    with cache._cond:
        cache._cond.wait_for(
            lambda: key not in cache._busy or cache._memory.live(query) is not None, patience
        )
        live = cache._memory.live(query)
    return None if live is None else list(live)


def _take_live(cache: Any, query: str, patience: float) -> list[Plan]:
    """A live circle: waited for when one runs, counted ahead of the background otherwise."""
    key = query.strip()
    if (live := _landed(cache, query, patience)) is not None:
        return live
    with cache._cond:
        if (refused := cache._memory.refusal(query)) is not None:
            raise refused
        cache._busy.add(key)  # after the patience: count beside the stuck one, not play from disk
        cache._urgent = [queued for queued in cache._urgent if queued != key]
        cache._stale.discard(key)
    with cache._counting(query), cache._hold():
        plans: list[Plan] = cache.circle(query)
    cache._remember(query, plans)
    return plans


__all__ = ["_landed", "_take_live"]
