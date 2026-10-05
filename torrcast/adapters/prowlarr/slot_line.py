"""Prowlarr's host queues as this process drew them, with the requests that have not left yet.

A drawn request waits here until half a pace before its slot, and Prowlarr queues by arrival,
so while it waits its place is still ours to move. The viewer's text takes the place of a name
not gone yet: on the stand a shelf's search drew Knaben for its two names, the viewer's search
a moment later drew its text behind them, the names were kept back unsent when their circle
ended, and the text still waited out both of their slots, 6.9 s on an empty queue ("Призрак в
доспехах 2026", 10.1 s where dev took 3.4, stand 05.10). A name kept back gives its place to
the ones behind it.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import NamedTuple


@dataclass(slots=True)
class _Wait:
    start: float
    spare: bool


class SlotLine:
    """Where each host's next slot starts and where each request still waiting starts now."""

    class Slot(NamedTuple):
        """A drawn slot: seconds it stands in the queue, its start and its ticket in the line."""

        queued: float
        start: float
        ticket: int

    def __init__(self, pace: float) -> None:
        self._pace = pace
        self._tickets = itertools.count(1)
        self._free: dict[str, float] = {}
        self._lead: dict[str, float] = {}  # where the last request that is always sent starts
        self._waits: dict[str, dict[int, _Wait]] = {}

    def draw(self, name: str, budget: float, now: float, *, spare: bool) -> SlotLine.Slot | None:
        """Draw ``name``'s next slot at ``now``; None for a ``spare`` one past its ``budget``.

        A request the search needs (not ``spare``) goes ahead of every name still waiting to
        leave after ``now``; those move a pace on.
        """
        start = max(now, self._free.get(name, now))
        if spare and start - max(now, self._lead.get(name, now)) >= budget:
            return None
        self._free[name] = start + self._pace
        waits = self._waits.setdefault(name, {})
        if not spare:
            soon = now + self._pace / 2  # a name leaving by then is in Prowlarr ahead of the text
            start = min(
                [start, *(one.start for one in waits.values() if one.spare and one.start > soon)]
            )
            for one in waits.values():
                if one.start >= start:
                    one.start += self._pace
            self._lead[name] = start
        ticket = next(self._tickets)
        waits[ticket] = _Wait(start, spare)
        return SlotLine.Slot(start - now, start, ticket)

    def lag(self, name: str, now: float) -> float:
        """Seconds till ``name``'s next slot: zero or less while its queue is empty."""
        return self._free.get(name, now) - now

    def start(self, name: str, ticket: int) -> float | None:
        """Where the ticket's slot starts now; None once it left or was given back."""
        one = self._waits.get(name, {}).get(ticket)
        return None if one is None else one.start

    def leave(self, name: str, ticket: int) -> None:
        """The ticket's request went to Prowlarr: its place is no longer ours to move."""
        self._waits.get(name, {}).pop(ticket, None)

    def give_back(self, name: str, ticket: int) -> None:
        """The ticket's request never goes: the slots behind it move a pace up."""
        gone = self._waits.get(name, {}).pop(ticket, None)
        if gone is None:
            return
        for one in self._waits[name].values():
            if one.start > gone.start:
                one.start -= self._pace
        self._free[name] -= self._pace
        if self._lead.get(name, gone.start) > gone.start:
            self._lead[name] -= self._pace


__all__ = ["SlotLine"]
