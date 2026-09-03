"""Names shared by the torrcast integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "torrcast"
#: The serve listens here; the port is part of the contract, not a preference.
DEFAULT_PORT: Final = 8479
#: A show moves, so it is polled often; an idle box is asked six times more rarely.
SCAN_INTERVAL_SHOWING: Final = timedelta(seconds=5)
SCAN_INTERVAL_IDLE: Final = timedelta(seconds=30)
#: States that mean something is on the screen right now.
SHOWING_STATES: Final = frozenset({"starting", "playing", "paused"})
#: Volume is absolute on the wire, so a step is added here and sent as a level.
VOLUME_STEP: Final = 0.05
#: Seconds; the serve answers from the local network and has no reason to be slow.
REQUEST_TIMEOUT: Final = 10
#: Seconds; a search walks out to the indexers, not just the local network.
#:
#: Measured on the stand: a cold search answered in 11.0 s while the shared
#: :data:`REQUEST_TIMEOUT` (10 s) was already spent, and the entry field told a person
#: the search failed while the serve was still working on it. The serve itself waits up
#: to 150 s for one stuck indexer before it gives up
#: (``torrcast.adapters.prowlarr.prowlarr_api.TIMEOUT``); a search timeout shorter than
#: that can cut off an answer the serve would still have delivered. Margin is added on
#: top of that ceiling, not on top of the one cold measurement.
SEARCH_REQUEST_TIMEOUT: Final = 160
