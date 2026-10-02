"""The mark of a warmup circle: it gives way to a viewer in Prowlarr's queues.

:meth:`~torrcast.adapters.prowlarr.host_slots.HostSlots.give_way` holds only the circles
counted under this mark. A pool that asks for the circle carries the mark along only when it
runs each ask in a copy of the caller's context (:func:`contextvars.copy_context`).

A viewer who asks for the very request a warmup circle counts makes the circle his own
(:data:`TAKEN`): from then on it gives way to no one, as his own would not.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import threading

#: The circle runs for the warmup, not for a viewer.
WARMUP: ContextVar[bool] = ContextVar("warmup", default=False)
#: Set once a viewer took the warmup's circle over.
TAKEN: ContextVar[threading.Event | None] = ContextVar("taken", default=None)


@contextmanager
def warmup(taken: threading.Event | None = None) -> Iterator[None]:
    """The circles counted in this block are the warmup's, until ``taken`` is set."""
    token = WARMUP.set(True)
    seat = TAKEN.set(taken)
    try:
        yield
    finally:
        TAKEN.reset(seat)
        WARMUP.reset(token)


__all__ = ["TAKEN", "WARMUP", "warmup"]
