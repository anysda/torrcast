"""How long one circle of indexers waits before it hands over what has answered."""

from __future__ import annotations

import time
from collections.abc import Sequence

from torrcast.adapters.prowlarr.spawn_ask import _Ask
from torrcast.domain.quorum_indexer import quorum_indexer
from torrcast.domain.wait_indexer import wait_indexer


def circle_wait(
    asked: Sequence[_Ask], *, names: bool, began: float, slack: float, held: float = 0.0
) -> list[_Ask]:
    """Wait for the circle's core and return it; the rest answer in time or come late.

    The core are the indexers the pool must not do without
    (:func:`~torrcast.domain.wait_indexer.wait_indexer`). A circle of the picture's
    ``names`` only adds rows: the viewer's text answers for the catalogue's health, so the
    quorum does not hold it. With no core at all, the anime fallback, every one is waited:
    otherwise there would be nobody to wait and the circle would come back empty.

    ``held`` is the budget of a core indexer left unsent
    (:class:`~torrcast.adapters.prowlarr.host_slots.HostSlots`): its request could not
    start in time, and it used to hold the circle exactly that long. The circle still
    gives the others that time, so no row that came before comes late now, but it no
    longer falls back to waiting every one in full.
    """
    core = [
        ask for ask in asked if wait_indexer(ask.name) and not (names and quorum_indexer(ask.name))
    ] or ([] if held else list(asked))
    for ask in core:
        # Every budget runs from the circle's start: waiting one after another from
        # the call added the first answer's seconds to the next silent one's budget.
        ask.done.wait(max(0.0, began + ask.budget + slack - time.monotonic()))
    for ask in asked:
        ask.done.wait(max(0.0, began + held - time.monotonic()))
    return core


__all__ = ["circle_wait"]
