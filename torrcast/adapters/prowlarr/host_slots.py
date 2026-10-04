"""Prowlarr's pacing seen from this process: when each indexer can take the next request.

Prowlarr paces requests by the host string: each waits two seconds behind the one before it,
in the order they arrive (:mod:`torrcast.domain.joint_query`). A request we stopped waiting
for is not taken back: it keeps its slot in that queue. The second of the picture's names
drew the third slot at every host, four seconds in, and a three-second budget could never
see its answer; on the stand, with searches under four seconds, the next search's own text
drew its slot behind that one and went silent too, a query after another. The queue lives in
Prowlarr across searches, so its picture lives here, in the process, and not in one client.

The viewer goes first in these queues (:meth:`HostSlots.give_way`). After a restart the saved
screen's warmup queued sixteen requests at YTS; the last ones started past YTS's six-second
budget and the book counted the source as down (three restarts: 17, 12 and 13 silences),
although YTS answered each one in 0.4 s. A warmup circle now starts only when no live search
runs and none of its hosts has a request of ours still in flight, so it holds one slot at
most ahead of a viewer. The drawn slots alone did not do: Prowlarr runs YTS 2.5 s apart, not
two, and warmup circles spaced by the picture still stacked YTS half a second per circle
(three restarts: 12, 12 and 13 silences, every circle leaving YTS late).

A request cannot be taken back, so a warmup must not send one a search is about to need.
After a restart the saved screen's circle left 0.68 s before the first search, and the
search's JacRed text started a whole pace behind it (+1.32 s, the warmup's at -0.67 s). The
warmup now also waits out :data:`QUIET` without a live search, counted from the start of the
process and again from the end of every search (:meth:`HostSlots.still`), and it waits so
before it takes a request: a viewer of the very request then counts it himself.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from typing import Final

from torrcast.adapters.prowlarr.warmup import TAKEN, WARMUP
from torrcast.ports.journal.slot import journal

#: Prowlarr's pause between two requests to one host.
PACE: Final = 2.0
#: Longest a warmup circle gives way: live searches back to back do not starve it for good.
MOST: Final = 60.0
#: How often a waiting warmup looks at the queues again while no live search ends.
LOOK: Final = 0.25
#: Seconds without a live search before a warmup circle starts: the next search of one process
#: came within 15.2 s of the one before in nine cases of ten (2925 on the stand, median 6.0 s).
QUIET: Final = 15.0


class HostSlots:
    """When each indexer's next slot starts, as drawn by the requests this process sent."""

    def __init__(
        self, clock: Callable[[], float] = time.monotonic, pace: float = PACE, quiet: float = QUIET
    ) -> None:
        self._clock = clock
        self._pace = pace
        self._quiet = quiet
        self._calm = clock()  # the start of the process counts as a search just ended
        self._ended: float | None = None  # the end of the last live search, none yet
        self._lock = threading.Lock()
        self._free: dict[str, float] = {}
        self._flight: dict[str, list[threading.Event]] = {}
        self._turn = threading.Condition(self._lock)
        self._live = 0

    def take(self, name: str, budget: float, *, spare: bool = False) -> bool:
        """Draw ``name``'s next slot for a request waited ``budget`` seconds.

        ``spare`` is a request the search can do without, the picture's names: one whose slot
        starts at its budget or later could not answer in it, so it is not sent at all and
        leaves the slot to the next one. The viewer's text is always sent: it makes the tiles.
        """
        return self.draw(name, budget, spare=spare) is not None

    def draw(self, name: str, budget: float, *, spare: bool = False) -> float | None:
        """As :meth:`take`, and the seconds the request stands in the host's queue."""
        slot = self.claim(name, budget, spare=spare)
        return None if slot is None else slot[0]

    def claim(self, name: str, budget: float, *, spare: bool = False) -> tuple[float, float] | None:
        """As :meth:`draw`, with the slot's start on this clock for :meth:`give_back`."""
        with self._lock:
            now = self._clock()
            start = max(now, self._free.get(name, now))
            if spare and start - now >= budget:
                return None
            self._free[name] = start + self._pace
            return start - now, start

    def give_back(self, name: str, start: float) -> None:
        """A request drawn at ``start`` never left for Prowlarr: the host's last slot is free."""
        with self._lock:
            if self._free.get(name) == start + self._pace:
                self._free[name] = start

    def sent(self, name: str, done: threading.Event) -> None:
        """A request to ``name`` is in flight until ``done`` is set."""
        with self._lock:
            self._flight[name] = [
                *(one for one in self._flight.get(name, []) if not one.is_set()),
                done,
            ]

    @contextmanager
    def live(self) -> Iterator[None]:
        """A viewer's search runs while this block does: warmup circles wait for its end."""
        with self._turn:
            self._live += 1
            self._turn.notify_all()  # a warmup circle the viewer took over stops giving way
        try:
            yield
        finally:
            with self._turn:
                self._live -= 1
                self._calm = self._ended = self._clock()
                self._turn.notify_all()

    def still(self, began: float, most: float = MOST) -> float:
        """Seconds the warmup still keeps off the network, waiting since ``began``.

        It waits before it takes the next request, not in :meth:`give_way`: a taken request
        made the viewer who asked for it wait the whole pause behind the warmup's claim (a
        shelf tile on the stand: 18.5 s, against 5.0 s without the warmup).
        """
        with self._lock:
            now = self._clock()
            return min(self._calm + self._quiet - now, began + most - now)

    def hold_off(self, sleep: Callable[[float], None] = time.sleep, most: float = MOST) -> None:
        """Return once no search runs and :meth:`still` lets a warmup on the network.

        ``most`` seconds at the longest: searches back to back do not hold it for good.
        """
        began = self._clock()
        while self._clock() < began + most:
            left = self.still(began, most)
            if left <= 0 and not self._live:
                return
            sleep(min(left, LOOK) if left > 0 else LOOK)

    def after_search(self, began: float, most: float = MOST) -> float:
        """Seconds a shelf's background circle still waits, waiting since ``began``.

        As :meth:`still`, but only behind a viewer's search, running or ended under
        :data:`QUIET` ago: the start of the process does not count, the shelf fills at once.
        The shelf's circles went as a viewer's and stood in Prowlarr's host queues ahead of
        him: his text started there 4.9 s after his search (median of 15 on the stand).
        """
        with self._lock:
            now = self._clock()
            if self._live:
                return began + most - now
            if self._ended is None:
                return 0.0
            return min(self._ended + self._quiet - now, began + most - now)

    def give_way(self, names: Sequence[str], most: float = MOST) -> float:
        """The moment (:func:`time.monotonic`) a circle to ``names`` may start.

        A viewer's circle is never held. A warmup circle waits until no live search runs and
        none of its hosts has a queue or a request in flight, ``most`` seconds at the longest.
        A warmup circle a viewer took over (:data:`TAKEN`) is his: it goes at once. Held as
        warmup, it kept the viewer of that very tile 33.2 s with Knaben silent, 3.2 s without.
        """
        taken = TAKEN.get()
        if not WARMUP.get() or (taken is not None and taken.is_set()):
            return time.monotonic()
        began = self._clock()
        with self._turn:
            while True:
                now = self._clock()
                lag = max((self._free.get(name, now) - now for name in names), default=0.0)
                flying = any(
                    not one.is_set() for name in names for one in self._flight.get(name, [])
                )
                free = self._live == 0 and lag <= 0 and not flying
                if free or now >= began + most or (taken is not None and taken.is_set()):
                    break
                self._turn.wait(min(began + most - now, max(lag, LOOK)))
        if (held := now - began) > LOOK:
            journal().emit("search", "warmup_gave_way", held=round(held, 2), names=list(names))
        return time.monotonic()


#: The one queue picture of the process: the clients live one search each.
HOST_SLOTS: Final = HostSlots()

__all__ = ["HOST_SLOTS", "LOOK", "MOST", "PACE", "QUIET", "HostSlots"]
