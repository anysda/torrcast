"""Circle only from the network: the renewal of a show whose circle from disk gave no release.

A circle from disk stood for hours: releases left the pool, and the one release of the Rick
and Morty s2e1 row that plays was not in it. The show still starts on such a circle at once;
only when its selection ends with nothing does it ask for this one (:mod:`web.show_stage`).
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import threading

    from torrcast.usecases.select.plan import Plan
    from web.circle_memory import CircleMemory


class _Cache(Protocol):
    """What of :class:`web.warm_cache.WarmCache` the live take reaches for."""

    _cond: threading.Condition
    _busy: set[str]
    _urgent: list[str]
    _stale: set[str]
    _memory: CircleMemory

    @property
    def circle(self) -> Callable[[str], list[Plan]]: ...

    def _counting(self, query: str) -> AbstractContextManager[None]: ...

    def _hold(self) -> AbstractContextManager[None]: ...

    def _remember(self, query: str, plans: list[Plan], revived: bool = False) -> None: ...


def _landed(cache: _Cache, query: str, patience: float) -> list[Plan] | None:
    """A live circle, waiting for the one that runs; ``None`` - none runs, count your own."""
    key = query.strip()
    with cache._cond:
        cache._cond.wait_for(
            lambda: key not in cache._busy or cache._memory.live(query) is not None, patience
        )
        live = cache._memory.live(query)
    return None if live is None else list(live)


def _take_live(cache: _Cache, query: str, patience: float) -> list[Plan]:
    """A live circle: waited for when one runs, counted ahead of the background otherwise."""
    key = query.strip()
    if (live := _landed(cache, query, patience)) is not None:
        return live
    with cache._cond:
        if (refused := cache._memory.refusal(query)) is not None:
            raise refused
        cache._busy.add(key)  # after the patience: count beside the stuck one, not the disk
        cache._urgent = [queued for queued in cache._urgent if queued != key]
        cache._stale.discard(key)
    with cache._counting(query), cache._hold():
        plans = cache.circle(query)
    cache._remember(query, plans)
    return plans


__all__ = ["_take_live"]
