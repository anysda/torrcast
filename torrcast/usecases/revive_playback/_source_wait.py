"""Bound the wait for a missing continuation independently of receiver state."""

from dataclasses import dataclass

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.domain.revive_settings import REVIVE_LIMIT
from torrcast.usecases.feed_pack.feed import Feed
from torrcast.usecases.rank._hms import _hms


@dataclass(slots=True)
class _SourceWait:
    """Only a moving position or a supplied continuation ends this wait."""

    position: float = -1.0
    since: float = -1.0

    def check(self, feed: Feed, pos: float, inactive: bool, now: float) -> None:
        """Pause and dead sessions have their own deadlines in the caller."""
        front = feed.front(pos)
        supplied = front > pos and front >= feed.grid.end(feed.grid.slot_at(pos) + 1)
        if inactive or supplied or pos != self.position:
            self.since = now
        self.position = pos
        if now - self.since >= REVIVE_LIMIT:
            raise InfraError(
                phrase("revive.source_wait_ended", secs=f"{REVIVE_LIMIT:.0f}", pos=_hms(pos))
            )
