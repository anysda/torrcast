"""How long the picture's names wait for the viewer's text to leave first."""

from __future__ import annotations

from torrcast.adapters.prowlarr.host_slots import MOST
from torrcast.adapters.prowlarr.warmup import WARMUP


def names_head(wait: float) -> float:
    """The names' head start ``wait``, and a warmup's text's stand in the queues on top.

    A warmup's text stands in :meth:`~torrcast.adapters.prowlarr.host_slots.HostSlots.give_way`
    up to :data:`MOST`. Names let go after ``wait`` stood there beside it and, the circle taken
    over by a viewer, drew RuTor's and YTS's next slot ahead of his text: it left 2.1 s and
    2.5 s after his ask, not at once.
    """
    return wait + MOST if WARMUP.get() else wait


__all__ = ["names_head"]
