"""When an indexer that keeps silent is down: three states, not two.

An indexer *answered* when its rows came in the time the first circle waits its core,
:data:`IN_TIME`. It is *down* when Prowlarr holds it out (``disabledTill``, the circle never
asks it), or when it kept silent :data:`DOWN_AFTER` times in a row, each within
:data:`DOWN_WINDOW` of the one before. Anything short of that is *unknown*: one refusal of
the network is not a verdict. A down indexer is still asked, only not waited, so its first
answer in time brings it back.

The numbers come from the stand's trace of 315 circles (28-29.09): runs of Knaben's silence
that ended in an answer were 1 (8 times), 2 (5), 3 (4) and longer (6), so one or two
silences say nothing, and 96.7% of the gaps between two silences in a row were within half
an hour (98.4% within an hour). Prowlarr's own back-off keeps the idea of a ladder
(GPL-3.0, only the idea is taken): it will not hold an indexer out on its first failure.
"""

from __future__ import annotations

from typing import Final

from torrcast.domain.circle_budget import FIRST_CIRCLE_TIMEOUT

#: Silences in a row that make an indexer down.
DOWN_AFTER: Final = 3
#: Seconds between two silences that still count as one run; older knowledge is stale.
DOWN_WINDOW: Final = 1800.0
#: Seconds an answer may take and still be one: the first circle's cap and the second the
#: circle gives the thread to raise its flag (``indexer_circle.ASK_SLACK``).
IN_TIME: Final = FIRST_CIRCLE_TIMEOUT + 1.0

#: One indexer's run of silence: how many in a row and the wall-clock second of the last.
Run = tuple[int, float]


def is_down(run: Run | None, now: float) -> bool:
    """Down: enough silences in a row, and the last is not stale."""
    return run is not None and run[0] >= DOWN_AFTER and now - run[1] <= DOWN_WINDOW


__all__ = ["DOWN_AFTER", "DOWN_WINDOW", "IN_TIME", "Run", "is_down"]
