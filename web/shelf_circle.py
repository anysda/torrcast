"""The circle of a shelf tile's verdict: counted in the background, behind the viewer.

The verdict asked :meth:`web.warm_cache.WarmCache.take`, the viewer's own take, so the
shelf's circles went one after another as a viewer's would, whenever the shelf judged. On
the warm stand Prowlarr then started the viewer's text 4.9 s after his search (median of
15), behind the shelf's requests at the same hosts. Here the shelf waits out a viewer's
search and :data:`~torrcast.adapters.prowlarr.host_slots.QUIET` after it
(:meth:`~torrcast.adapters.prowlarr.host_slots.HostSlots.after_search`), and counts the
circle as the warmup does: it gives way in the host queues, and a viewer who asks for the
same tile takes it over (:func:`web.warm_pump._adopted`).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from torrcast.adapters.prowlarr.host_slots import HOST_SLOTS, LOOK, HostSlots
from torrcast.adapters.prowlarr.warmup import warmup
from web.warm_cache import BUSY_WAIT
from web.warm_pump import _claim, _turn
from web.warm_seat import WarmSeat

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan
    from web.warm_cache import WarmCache


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
        seat = WarmSeat()
        if stale is not None:
            cache._seats[key] = seat
        else:  # another hand counts it: wait for its end, never take a warmup circle over
            cache._cond.wait_for(lambda: key not in cache._busy, BUSY_WAIT)
    if stale is not None:
        with warmup(seat):
            _turn(cache, key, stale, urgent=False)
    if (refused := cache._memory.refusal(query)) is not None:
        raise refused
    plans = cache.ready(query)
    return cache.take(query) if plans is None else plans  # never counted: the viewer's way


__all__ = ["shelf_circle"]
