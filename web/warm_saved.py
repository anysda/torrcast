"""The saved home screen's startup warmup."""

from __future__ import annotations

from torrcast.ports.state_store.slot import store
from web.shelf_warm_targets import shelf_warm_targets
from web.shelves import _cache
from web.warm_targets import WarmTarget


def warm_saved() -> None:
    """Start disk-cached visible tiles, then Continue and later tiles, before a request."""
    saved = _cache._load()
    if saved.get("built_at") is not None:
        later = _continued() + shelf_warm_targets(saved, later=True)
        _cache.warm(shelf_warm_targets(saved), later)


def _continued() -> list[WarmTarget]:
    """The Continue row as ``GET /api/history`` lists it: unwatched, newest first."""
    entries = sorted(store().load().entries.items(), key=lambda kv: kv[1].updated, reverse=True)
    return [
        (entry.query or entry.title, key, entry.title, entry.year, entry.kind)
        for key, entry in entries
        if not entry.watched and entry.year and entry.kind in {"movie", "tv"}
    ]


__all__ = ["warm_saved"]
