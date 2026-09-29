"""Сезоны картины, у которых есть раздачи в круге поиска: доказательство выхода без даты.

Спрашивает плашка следующей серии (:mod:`hass.catalog_next`) каждую секунду опроса
состояния, поэтому круг читается только из памяти (:meth:`web.warm_cache.WarmCache.ready`):
нет его там - греется фоном (:meth:`web.warm_cache.WarmCache.hint`), а вердикт помнится.
Сорванный сетью круг (:class:`web.torn_circle.TornCircle`) вердиктом не считается.
"""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic
from typing import Final, Protocol

from torrcast.domain.seasons_named import seasons_named
from torrcast.usecases.select.plan import Plan
from web.torn_circle import TornCircle
from web.warm_wiring import WARM

#: Сколько помнится, какие сезоны картины видел пул: сезон на глазах не появляется.
KEEP: Final = 3600.0


class _Pool(Protocol):
    def ready(self, query: str) -> list[Plan] | None: ...
    def hint(self, query: str) -> int: ...


_seen: dict[tuple[str, str], tuple[tuple[int, ...], float]] = {}


def released_seasons(
    key: str, query: str, pool: _Pool = WARM, clock: Callable[[], float] = monotonic
) -> tuple[int, ...] | None:
    """Сезоны картины ``key`` с раздачами в круге ``query``; ``None`` - круг ещё греется."""
    memo = _seen.get((key, query))
    if memo is not None and clock() - memo[1] < KEEP:
        return memo[0]
    plans = pool.ready(query)
    if plans is None:
        pool.hint(query)
        return None
    if isinstance(plans, TornCircle):
        return None  # a circle torn by the network says nothing about seasons
    plan = next((plan for plan in plans if plan.picture.key == key), None)
    seasons = seasons_named(plan.picture) if plan is not None else ()
    _seen[(key, query)] = (seasons, clock())
    return seasons


__all__ = ["released_seasons"]
