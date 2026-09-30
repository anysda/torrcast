"""Send one circle: each indexer its own text, its own budget and its slot at the host."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from torrcast.adapters.prowlarr.host_slots import HostSlots
from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi
from torrcast.adapters.prowlarr.spawn_ask import _Ask, _follow, _in_flight, spawn_ask
from torrcast.domain.circle_indexers import Indexer
from torrcast.domain.joint_query import joint_query


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
        elif slots.take(name, cut, spare=joint is not None):
            asked.append(spawn_ask(api, text, limit, num, name, cut))
            slots.sent(name, asked[-1].done)
        else:
            unsent.append((name, cut))
    return asked, unsent


__all__ = ["send_circle"]
