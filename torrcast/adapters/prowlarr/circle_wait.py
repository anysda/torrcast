"""How long one circle of indexers waits before it hands over what has answered."""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Final

from torrcast.adapters.prowlarr.down_book import DOWN_BOOK, DownBook
from torrcast.adapters.prowlarr.spawn_ask import _Ask
from torrcast.domain.is_down import IN_TIME
from torrcast.domain.quorum_indexer import quorum_indexer
from torrcast.domain.wait_indexer import wait_indexer

#: How often a lone core's wait looks whether the others have all answered.
_STEP = 0.05

#: Seconds the viewer's text still waits the quorum once the rest of its core has answered
#: and the pool has rows. Prowlarr History on the stand (06-30.09, 22083 texts asked of
#: Knaben with RuTor or JacRed): Knaben ended after the last of them by more than 0.5 s in
#: 35.7%, 1.0 s in 26.2%, 1.5 s in 19.4%, 3.0 s in 14.2%. Past a second the tail hardly
#: thins: a Knaben not in by then mostly came seconds later (p90 5.2 s behind the others).
QUORUM_GRACE: Final = 1.0


def circle_wait(
    asked: Sequence[_Ask],
    *,
    names: bool,
    began: float,
    slack: float,
    unsent: Sequence[tuple[str, float]] = (),
    book: DownBook = DOWN_BOOK,
    grace: float = QUORUM_GRACE,
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
    is down, the circle waits the others asked, as a circle without a core does: in a
    circle of names JacRed is often the only core, and a down one held it to its 5 s zero.
    Only when every one asked is down there is nobody better to wait, and the circle waits
    them as it did. A down one that answers still revives, waited or not. A core one
    the circle gave up on after the whole first circle's wait is a silence told at once:
    its thread may live 45 s more, and a restart before that would never tell it.

    A circle of names whose only live core is one source ends when that one answers or
    when every other one asked has, whichever comes first. Its names go out with its text,
    and Prowlarr runs the second request two seconds behind the first: with JacRed's origin
    at its 5 s cut the answer could never come inside the circle's 7 s. On the stand (38
    circles of names with JacRed and others, 30.09) JacRed alone held eleven to the end,
    1.0 to 3.3 s after the last of the others had answered, and never answered in them.
    Ending with the others kept 20 of its 27 answers in time, every one with more than one
    row among them, lost seven with three rows between them, and shortened ten circles
    (7015 to 881 ms, 7004 to 5662). What it brings later comes late, and a circle ended by
    the others does not tell it silent: it was not waited its whole budget.

    The viewer's text waits the quorum only ``grace`` seconds past the rest of its core once
    the pool has rows: Knaben's own answer took 5-8 s where the others were in within a
    second, and the viewer waited it for rows the others had already brought. It comes late,
    as any other one the circle did not wait, and is not told silent. An empty pool still
    waits it whole: without the quorum an empty list proves nothing.
    """
    down = book.down()
    held = max(
        (budget for name, budget in unsent if _core(name, names=names) and name not in down),
        default=0.0,
    )
    waited = [ask for ask in asked if _core(ask.name, names=names)]
    live = [ask for ask in waited if ask.name not in down]
    alive = [ask for ask in asked if ask.name not in down]
    core = live or ([] if held else alive or waited or list(asked))
    others = [ask for ask in alive if ask not in live]
    if names and len(live) == 1 and others and not held:
        core = _first(live[0], others, began + live[0].budget + slack)
    elif not names and not held:
        core = _past_the_quorum(core, asked, began + slack, grace)
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


def _first(one: _Ask, others: Sequence[_Ask], until: float) -> list[_Ask]:
    """Wait ``one`` until ``until``, or until every one of ``others`` has answered."""
    while not one.done.is_set() and not all(ask.done.is_set() for ask in others):
        if (left := until - time.monotonic()) <= 0:
            break
        one.done.wait(min(left, _STEP))
    return list(others) if not one.done.is_set() and time.monotonic() < until else [one]


def _past_the_quorum(
    core: list[_Ask], asked: Sequence[_Ask], start: float, grace: float
) -> list[_Ask]:
    """Wait the rest of the core, then the quorum ``grace`` more if the pool has rows."""
    quorum = [ask for ask in core if quorum_indexer(ask.name)]
    rest = [ask for ask in core if ask not in quorum]
    if not quorum or not rest:
        return core
    for ask in rest:
        ask.done.wait(max(0.0, start + ask.budget - time.monotonic()))
    if not any(ask.rows for ask in asked if ask.done.is_set()):
        return core
    until = time.monotonic() + grace
    for ask in quorum:
        ask.done.wait(max(0.0, min(until, start + ask.budget) - time.monotonic()))
    # One its own budget ended before the grace did was waited whole: its silence is told.
    kept = [ask for ask in core if ask in rest or ask.done.is_set() or start + ask.budget <= until]
    for ask in core:
        ask.waived = ask not in kept
    return kept


def _core(name: str, *, names: bool) -> bool:
    return wait_indexer(name) and not (names and quorum_indexer(name))


__all__ = ["QUORUM_GRACE", "circle_wait"]
