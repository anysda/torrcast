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
