"""The hands of :class:`web.warm_cache.WarmCache`: the background queue and the card's own."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from typing import TYPE_CHECKING, Protocol

from torrcast.adapters.prowlarr.warmup import warmup
from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.torrcast_error import TorrcastError
from web.start_first import start_first
from web.warm_priority import _hint

if TYPE_CHECKING:
    import threading

    from torrcast.usecases.select.plan import Plan
    from web.circle_memory import CircleMemory


class _Cache(Protocol):
    """What of :class:`web.warm_cache.WarmCache` the background hand reaches for."""

    _cond: threading.Condition
    _queue: list[str]
    _urgent: list[str]
    _busy: set[str]
    _stale: set[str]
    _running: int
    _rushing: bool
    _memory: CircleMemory

    @property
    def circle(self) -> Callable[[str], list[Plan]]: ...

    def ready(self, query: str) -> list[Plan] | None: ...

    def _quiet(self) -> None: ...

    def _hold(self) -> AbstractContextManager[None]: ...

    def _remember(self, query: str, plans: list[Plan], revived: bool = False) -> None: ...


def _pump(cache: _Cache) -> None:
    """Take from the queue until it ends, giving way to a live request and a show start.

    A background circle adds its releases to TorrServer and reads their heads, the same
    swarm reads a starting show waits for (:mod:`web.start_first`). The card's own hand
    (:func:`_rush`) does not wait: it is the person's click.

    A screen is warmed from disk offline. A card (the urgent queue) woke a circle from disk:
    the show starts on it at once, and it is refreshed from the network right behind, so a
    selection that ends with nothing finds the new releases already landed.
    """
    try:
        while True:
            start_first()
            cache._quiet()
            with cache._cond:
                if not cache._urgent and not cache._queue:
                    return
                urgent = bool(cache._urgent)
                query = cache._urgent.pop(0) if urgent else cache._queue.pop(0)
                stale = _claim(cache, query)
            if stale is not None:
                with nullcontext() if urgent else warmup():
                    _turn(cache, query, stale, urgent)
    finally:
        with cache._cond:
            cache._running -= 1


def _rush(cache: _Cache) -> None:
    """The card's own hand: an open card does not wait for the background circle in flight.

    With one background hand the clicked card stood behind another tile's whole circle
    (7 s of an empty card on the stand). This hand takes only the urgent queue and holds the
    background back while it counts, so the click shares the indexers with one circle at most.
    """
    try:
        while True:
            with cache._cond:
                if not cache._urgent:
                    cache._rushing = False
                    return
                query = cache._urgent.pop(0)
                stale = _claim(cache, query)
            if stale is not None:
                with cache._hold():
                    _turn(cache, query, stale, urgent=True)
    finally:
        with cache._cond:
            cache._rushing = False


def _claim(cache: _Cache, query: str) -> bool | None:
    """Mark the circle as counted here; ``None`` when another hand or a live caller has it."""
    if query in cache._busy or (cache.ready(query) is not None and query not in cache._stale):
        return None  # a live caller already runs or landed this very circle
    cache._busy.add(query)
    stale = query in cache._stale
    cache._stale.discard(query)
    return stale


def _turn(cache: _Cache, query: str, stale: bool, urgent: bool) -> None:
    """Count one claimed circle, remember what it found and wake whoever waits for it."""
    kept: list[Plan] | None = None
    try:
        kept = None if stale else cache._memory.revive(query)
        plans: list[Plan] = cache.circle(query) if kept is None else kept
    except NotFoundError as nothing:
        cache._memory.refuse(query, nothing)
        plans = []
    except (TorrcastError, OSError) as broke:
        # Сорванный круг - тоже конец круга, и он помнится наравне с пустым. Пока
        # он не оставлял ни находки, ни отказа, согретого круга не появлялось
        # никогда, и карточка держала «ищем раздачи» до закрытия вкладки.
        cache._memory.refuse(query, _named(broke))
        plans = []
    cache._remember(query, plans, revived=kept is not None)
    with cache._cond:
        cache._busy.discard(query)
        cache._cond.notify_all()
    if kept is not None and urgent:
        _hint(cache, query, stale=True)


def _named(broke: TorrcastError | OSError) -> TorrcastError:
    """Сорвавшая круг беда словами продукта: у сети своих слов для зрителя нет."""
    return broke if isinstance(broke, TorrcastError) else InfraError(str(broke))


__all__ = ["_pump", "_rush"]
