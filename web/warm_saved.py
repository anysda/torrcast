"""The saved home screen's startup warmup."""

from __future__ import annotations

from web.shelves import _cache
from web.shelves_cache import _targets


def warm_saved() -> None:
    """Start disk-cached visible tiles before their first browser request."""
    saved = _cache._load()
    if saved.get("built_at") is not None:
        _cache.warm(_targets(saved))


__all__ = ["warm_saved"]
