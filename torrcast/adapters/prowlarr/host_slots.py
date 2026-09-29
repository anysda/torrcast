"""Prowlarr's pacing seen from this process: when each indexer can take the next request.

Prowlarr paces requests by the host string: each waits two seconds behind the one before it,
in the order they arrive (:mod:`torrcast.domain.joint_query`). A request we stopped waiting
for is not taken back: it keeps its slot in that queue. The second of the picture's names
drew the third slot at every host, four seconds in, and a three-second budget could never
see its answer; on the stand, with searches under four seconds, the next search's own text
drew its slot behind that one and went silent too, a query after another. The queue lives in
Prowlarr across searches, so its picture lives here, in the process, and not in one client.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Final

#: Prowlarr's pause between two requests to one host.
PACE: Final = 2.0


class HostSlots:
    """When each indexer's next slot starts, as drawn by the requests this process sent."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, pace: float = PACE) -> None:
        self._clock = clock
        self._pace = pace
        self._lock = threading.Lock()
        self._free: dict[str, float] = {}

    def take(self, name: str, budget: float, *, spare: bool = False) -> bool:
        """Draw ``name``'s next slot for a request waited ``budget`` seconds.

        ``spare`` is a request the search can do without, the picture's names: one whose slot
        starts at its budget or later could not answer in it, so it is not sent at all and
        leaves the slot to the next one. The viewer's text is always sent: it makes the tiles.
        """
        with self._lock:
            now = self._clock()
            start = max(now, self._free.get(name, now))
            if spare and start - now >= budget:
                return False
            self._free[name] = start + self._pace
            return True


#: The one queue picture of the process: the clients live one search each.
HOST_SLOTS: Final = HostSlots()

__all__ = ["HOST_SLOTS", "PACE", "HostSlots"]
