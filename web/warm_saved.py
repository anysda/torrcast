"""The saved home screen's startup warmup."""

from __future__ import annotations

import threading
from collections.abc import Callable

from torrcast.adapters.prowlarr.host_slots import HOST_SLOTS, HostSlots
from torrcast.ports.state_store.slot import store
from web.shelf_warm_targets import shelf_warm_targets
from web.shelves import _cache
from web.warm_targets import WarmTarget


def warm_saved(after: Callable[[], object] | None = None) -> None:
    """Start disk-cached visible tiles, then Continue and later tiles, before a request.

    The shelves rebuild starts here too, with the service: waiting for the first
    ``GET /api/shelves`` made the person who opened the page pay for the whole cold build.
    Given ``after``, it starts once that returns: built beside the catalogue's index, it
    held the index back, and with it the names of the first search after a restart.
    """
    saved = _cache._load()
    if saved.get("built_at") is not None:
        later = _continued() + shelf_warm_targets(saved, later=True)
        _cache.warm(shelf_warm_targets(saved), later)
    if after is None:
        _cache.start()
        return
    threading.Thread(
        target=_start_after, args=(after, HOST_SLOTS), daemon=True, name="shelves-after"
    ).start()


def _start_after(after: Callable[[], object], slots: HostSlots) -> None:
    """Start the rebuild once the map is built and the hosts are quiet.

    The rebuild's feed asked every indexer with an empty text right after the start, and the
    first search's own texts stood behind it in Prowlarr's host queues: its names ended at
    4.69 s against 3.06 s with the rebuild waiting the quiet (stand, 15 cold searches each).
    A page that asks for the shelves still starts them at once (``ShelvesCache.get``).
    """
    after()
    slots.hold_off()
    _cache.start()


def _continued() -> list[WarmTarget]:
    """The Continue row as ``GET /api/history`` lists it: unwatched, newest first."""
    entries = sorted(store().load().entries.items(), key=lambda kv: kv[1].updated, reverse=True)
    return [
        (entry.query or entry.title, key, entry.title, entry.year, entry.kind)
        for key, entry in entries
        if not entry.watched and entry.year and entry.kind in {"movie", "tv"}
    ]


__all__ = ["warm_saved"]
