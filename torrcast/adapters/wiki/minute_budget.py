"""Minute budget of Wikimedia requests shared by the card, the visible list and the background."""

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

#: Wikimedia counts a User-Agent client per minute across all its API sites and answers 429
#: over 200. The background stops short of it: the rest of the minute is left for clicks.
BACKGROUND_PER_MINUTE: Final = 160
#: The visible list's verdict goes past the background share, still below the site limit.
URGENT_PER_MINUTE: Final = 185
MINUTE: Final = 60.0
#: API sites share one counter and one quiet window; SPARQL has limits of its own.
API_HOSTS: Final = ("wikipedia.org", "wikidata.org", "wikimedia.org")
SPARQL_HOST: Final = "query.wikidata.org"
#: Image files are not API calls: no minute count, but a 429 there quiets the files alone.
UPLOAD_HOST: Final = "upload.wikimedia.org"
#: How long a group stays quiet after a 429 without ``Retry-After``, seconds.
QUIET_AFTER_429: Final = 5.0


@dataclass
class _Group:
    counted: bool
    sent: deque[float] = field(default_factory=deque)
    quiet_until: float = 0.0
    troubled_at: float = float("-inf")


class MinuteBudget:
    """Admit every card request and hold the rest inside the minute budget."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        pause: Callable[[float], None] = time.sleep,
    ) -> None:
        self.clock = clock
        self.pause = pause
        self.groups = {"api": _Group(counted=True), "upload": _Group(counted=False)}
        self.lock = threading.Lock()

    def admit(self, host: str, timeout: float, foreground: bool, urgent: bool = False) -> bool:
        """Count one request; the background waits for room until ``timeout``.

        An urgent request does not wait out a quiet window longer than its timeout: it is
        refused at once, and its caller asks again when the window ends (:meth:`calm_at`).
        """
        group = self._group(host)
        if group is None:
            return True
        deadline = self.clock() + timeout
        share = URGENT_PER_MINUTE if urgent else BACKGROUND_PER_MINUTE
        while True:
            with self.lock:
                now = self.clock()
                while group.sent and now - group.sent[0] >= MINUTE:
                    group.sent.popleft()
                full = group.counted and len(group.sent) >= share
                if foreground or (not full and now >= group.quiet_until):
                    group.sent.append(now)
                    return True
                free = max(group.sent[0] + MINUTE if full else now, group.quiet_until)
                if now >= deadline or (urgent and free > deadline):
                    group.troubled_at = now
                    return False
            self.pause(max(0.01, min(free, deadline) - now))

    def throttled(self, host: str, retry_after: str | None) -> None:
        """Keep the host's group quiet for as long as a 429 asks."""
        group = self._group(host)
        if group is None:
            return
        quiet = float(retry_after) if retry_after and retry_after.isdigit() else QUIET_AFTER_429
        with self.lock:
            now = self.clock()
            group.quiet_until = max(group.quiet_until, now + quiet)
            group.troubled_at = now

    def troubled_since(self, moment: float) -> bool:
        """A 429 or a local refusal came at or after ``moment``: a silence proves nothing."""
        with self.lock:
            return any(group.troubled_at >= moment for group in self.groups.values())

    def calm_at(self) -> float:
        """When every quiet window is over, on the budget's clock."""
        with self.lock:
            return max(self.clock(), *(group.quiet_until for group in self.groups.values()))

    def _group(self, host: str) -> _Group | None:
        if host == UPLOAD_HOST:
            return self.groups["upload"]
        if host == SPARQL_HOST or not host.endswith(API_HOSTS):
            return None
        return self.groups["api"]
