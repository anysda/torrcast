"""Delivery of a fact-flight update to its optional observer."""

from __future__ import annotations

import contextlib
from collections.abc import Callable


def tell(seen: Callable[[], None] | None) -> None:
    """Notify an observer without allowing its failure to stop the fact flight."""
    if seen is None:
        return
    with contextlib.suppress(Exception):
        seen()


__all__ = ["tell"]
