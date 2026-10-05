"""Names a circle no longer waits for, kept back before they take their host's slot."""

from __future__ import annotations

from collections.abc import Sequence

from torrcast.adapters.prowlarr.host_slots import HostSlots
from torrcast.adapters.prowlarr.spawn_ask import _Ask, _drop


def drop_unsent(asked: Sequence[_Ask], slots: HostSlots) -> list[str]:
    """Keep back the names that have not left when their circle ended; their indexers.

    Each gives its slot back: the requests drawn behind it move up a pace.
    """
    kept = [ask for ask in asked if _drop(ask)]
    for ask in kept:
        slots.give_back(ask.name, ask.slot)
    return [ask.name for ask in kept]


__all__ = ["drop_unsent"]
