"""The circle of a shelf tile's verdict: counted in the background, behind the viewer.

The verdict asked :meth:`web.warm_cache.WarmCache.take`, the viewer's own take, so the
shelf's circles went one after another as a viewer's would, whenever the shelf judged. On
the warm stand Prowlarr then started the viewer's text 4.9 s after his search (median of
15), behind the shelf's requests at the same hosts. Here the shelf waits out a viewer's
search and :data:`~torrcast.adapters.prowlarr.host_slots.QUIET` after it
(:meth:`~torrcast.adapters.prowlarr.host_slots.HostSlots.after_search`), then counts the
circle at once. Not as the warmup's: a warmup circle stands in the host queues while its
hosts have a queue or a request in flight, the warmup's own among them, up to 55 s a circle
on the cold stand, and the shelf judged 0 to 7 tiles in 150 s there against 10 to 12. Nor
as a live one: that counts as a viewer's search. The warmup only starts no new circle
meanwhile, as beside a live one: without that the shelf judged 11 and 12 tiles against 12 to 16.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from torrcast.adapters.prowlarr.host_slots import HOST_SLOTS, LOOK, HostSlots
from web.warm_cache import BUSY_WAIT
from web.warm_pump import _claim, _turn

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan
    from web.warm_cache import WarmCache


@contextmanager
def _beside(cache: WarmCache) -> Iterator[None]:
    """The warmup starts no new circle meanwhile, as beside a live one, but gives way to none."""
    with cache._cond:
        cache._live += 1
    try:
        yield
    finally:
        with cache._cond:
            cache._live -= 1
            cache._cond.notify_all()


def shelf_circle(
    cache: WarmCache,
    query: str,
    slots: HostSlots = HOST_SLOTS,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> list[Plan]:
    """The tile's circle: from memory at once, else counted once no viewer searches."""
    if cache.ready(query) is not None:
        return cache.take(query)
    began = clock()
    while (left := slots.after_search(began)) > 0:
        sleep(min(left, LOOK))
    key = query.strip()
    with cache._cond:
        stale = _claim(cache, key)
        if stale is None:  # another hand counts it: wait for its end, never take a warmup over
            cache._cond.wait_for(lambda: key not in cache._busy, BUSY_WAIT)
    if stale is not None:
        with _beside(cache):
            _turn(cache, key, stale, urgent=False)
    if (refused := cache._memory.refusal(query)) is not None:
        raise refused
    plans = cache.ready(query)
    return cache.take(query) if plans is None else plans  # never counted: the viewer's way


__all__ = ["shelf_circle"]
