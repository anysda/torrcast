"""The mark of a warmup circle: it gives way to a viewer in Prowlarr's queues.

:meth:`~torrcast.adapters.prowlarr.host_slots.HostSlots.give_way` holds only the circles
counted under this mark. A pool that asks for the circle carries the mark along only when it
runs each ask in a copy of the caller's context (:func:`contextvars.copy_context`).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

#: The circle runs for the warmup, not for a viewer.
WARMUP: ContextVar[bool] = ContextVar("warmup", default=False)


@contextmanager
def warmup() -> Iterator[None]:
    """The circles counted in this block are the warmup's."""
    token = WARMUP.set(True)
    try:
        yield
    finally:
        WARMUP.reset(token)


__all__ = ["WARMUP", "warmup"]
