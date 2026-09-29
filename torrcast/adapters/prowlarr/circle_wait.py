"""How long one circle of indexers waits before it hands over what has answered."""

from __future__ import annotations

import time
from collections.abc import Sequence

from torrcast.adapters.prowlarr.down_book import DOWN_BOOK, DownBook
from torrcast.adapters.prowlarr.spawn_ask import _Ask
from torrcast.domain.is_down import IN_TIME
from torrcast.domain.quorum_indexer import quorum_indexer
from torrcast.domain.wait_indexer import wait_indexer


def circle_wait(
    asked: Sequence[_Ask],
    *,
    names: bool,
    began: float,
    slack: float,
    unsent: Sequence[tuple[str, float]] = (),
    book: DownBook = DOWN_BOOK,
) -> list[_Ask]:
    """Wait for the circle's core and return it; the rest answer in time or come late.

    The core are the indexers the pool must not do without
    (:func:`~torrcast.domain.wait_indexer.wait_indexer`). A circle of the picture's
    ``names`` only adds rows: the viewer's text answers for the catalogue's health, so the
    quorum does not hold it. With no core at all, the anime fallback, every one is waited:
    otherwise there would be nobody to wait and the circle would come back empty.

    ``unsent`` are the names and budgets of requests left unsent
    (:class:`~torrcast.adapters.prowlarr.host_slots.HostSlots`): they could not start in
    time. One that would have been the core used to hold the circle exactly its budget,
    and the circle still gives the others that time, so no row that came before comes
    late now, but it no longer falls back to waiting every one in full. One outside the
    core, the quorum in a circle of names, never held it and holds nothing now.

    One the ``book`` holds down (:mod:`torrcast.domain.is_down`) is asked and not
    waited: a silent Knaben held every circle 7.0 s for nothing. When every one of the core
    is down there is nobody better to wait, and the circle waits them as it did. A core one
    the circle gave up on after the whole first circle's wait is a silence told at once:
    its thread may live 45 s more, and a restart before that would never tell it.
    """
    down = book.down()
    held = max(
        (budget for name, budget in unsent if _core(name, names=names) and name not in down),
        default=0.0,
    )
    waited = [ask for ask in asked if _core(ask.name, names=names)]
    live = [ask for ask in waited if ask.name not in down]
    core = live or waited or ([] if held else list(asked))
    for ask in core:
        # Every budget runs from the circle's start: waiting one after another from
        # the call added the first answer's seconds to the next silent one's budget.
        ask.done.wait(max(0.0, began + ask.budget + slack - time.monotonic()))
    for ask in asked:
        ask.done.wait(max(0.0, began + held - time.monotonic()))
    for ask in core:
        if ask.budget + slack >= IN_TIME and not ask.done.is_set() and ask.judge.acquire(False):
            book.hear(ask.name, answered=False)
    return core


def _core(name: str, *, names: bool) -> bool:
    return wait_indexer(name) and not (names and quorum_indexer(name))


__all__ = ["circle_wait"]
