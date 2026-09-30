"""Send one circle: each indexer its own text, its own budget and its slot at the host."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from torrcast.adapters.prowlarr.host_slots import HostSlots
from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi
from torrcast.adapters.prowlarr.spawn_ask import _Ask, _follow, _in_flight, spawn_ask
from torrcast.domain.circle_indexers import Indexer
from torrcast.domain.joint_query import joint_query
from torrcast.domain.quorum_indexer import quorum_indexer
from torrcast.domain.wait_indexer import wait_indexer


def send_circle(
    api: ProwlarrApi,
    slots: HostSlots,
    pairs: Sequence[Indexer],
    query: str,
    limit: int,
    joint: str | None,
    along: str = "",
    *,
    budgets: Callable[[str], float],
    cap: float,
) -> tuple[list[_Ask], list[tuple[str, float]]]:
    """Start every indexer that has a text to ask; return the asked and the unsent.

    ``joint`` marks a circle of the picture's names
    (:func:`~torrcast.domain.joint_query.joint_query`): it only adds rows, so a name
    whose request could not start within its budget behind Prowlarr's queue to the
    host (:meth:`~torrcast.adapters.prowlarr.host_slots.HostSlots.take`) is not sent.
    A budget is the indexer's own, cut to the circle's ``cap`` when there is one.
    The unsent come back with their budgets: the circle is held for them as long as
    their doomed request would have held it, and nobody heard their rows.
    ``along`` is the names the viewer's text takes to the indexer of joined texts.
    A request that stands in the host's queue gets its budget past its slot: RuTor's names
    left Prowlarr at +2.1 s and answered at +3.1 and +3.7, and a 3 s budget from the send
    lost them and told the book RuTor was silent (stand 30.09, "Начало" chose Batman).
    Only the core the circle waits gets the queue in its wait; the others get it in their
    request's life alone. A circle with its core down waits every other one, and AniLibria
    standing 7 s in the queue held "Выживший" to 10.9 s where dev ended at 7 (stand 01.10).
    A text already on its way to the indexer is not sent again: the circle waits that
    request (:func:`~torrcast.adapters.prowlarr.spawn_ask._follow`) and draws no slot.
    """
    asked: list[_Ask] = []
    unsent: list[tuple[str, float]] = []
    for num, name in pairs:
        text = joint_query(name, query, joint, along)
        if not text:
            continue
        cut = min(budgets(name), cap) if cap else budgets(name)
        if (twin := _in_flight(api, text, limit, num)) is not None:
            asked.append(_follow(twin, cut))
        elif (queued := slots.draw(name, cut, spare=joint is not None)) is not None:
            core = wait_indexer(name) and not (joint is not None and quorum_indexer(name))
            asked.append(
                spawn_ask(api, text, limit, num, name, cut + (queued if core else 0.0), queued)
            )
            slots.sent(name, asked[-1].done)
        else:
            unsent.append((name, cut))
    return asked, unsent


__all__ = ["send_circle"]
