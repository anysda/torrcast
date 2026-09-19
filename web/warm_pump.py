"""The one background hand of :class:`web.warm_cache.WarmCache`: queue, urgent card, refresh."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.torrcast_error import TorrcastError
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
    _memory: CircleMemory

    @property
    def circle(self) -> Callable[[str], list[Plan]]: ...

    def ready(self, query: str) -> list[Plan] | None: ...

    def _quiet(self) -> None: ...

    def _remember(self, query: str, plans: list[Plan], revived: bool = False) -> None: ...


def _pump(cache: _Cache) -> None:
    """Take from the queue until it ends, giving way to a live request.

    A screen is warmed from disk offline. A card (the urgent queue) woke a circle from disk:
    the show starts on it at once, and it is refreshed from the network right behind, so a
    selection that ends with nothing finds the new releases already landed.
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
    finally:
        with cache._cond:
            cache._running -= 1


def _named(broke: TorrcastError | OSError) -> TorrcastError:
    """Сорвавшая круг беда словами продукта: у сети своих слов для зрителя нет."""
    return broke if isinstance(broke, TorrcastError) else InfraError(str(broke))


__all__ = ["_pump"]
