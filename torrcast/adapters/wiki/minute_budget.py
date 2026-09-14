"""Minute budget of Wikipedia requests shared by the card and the background."""

import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Final

#: Wikimedia counts a User-Agent client per minute across all its sites and answers 429
#: over 200. The background stops short of it: the rest of the minute is left for clicks.
BACKGROUND_PER_MINUTE: Final = 160
MINUTE: Final = 60.0
#: Hosts counted by that limit here; SPARQL of query.wikidata.org is limited separately.
WIKI_HOSTS: Final = "wikipedia.org"
#: How long the background stays quiet after a 429 without ``Retry-After``, seconds.
QUIET_AFTER_429: Final = 5.0


class MinuteBudget:
    """Admit every card request and hold the background inside the minute budget."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        pause: Callable[[float], None] = time.sleep,
    ) -> None:
        self.clock = clock
        self.pause = pause
        self.sent: deque[float] = deque()
        self.quiet_until = 0.0
        self.lock = threading.Lock()

    def admit(self, host: str, timeout: float, foreground: bool) -> bool:
        """Count one Wikipedia request; the background waits for room until ``timeout``."""
        if not host.endswith(WIKI_HOSTS):
            return True
        deadline = self.clock() + timeout
        while True:
            with self.lock:
                now = self.clock()
                while self.sent and now - self.sent[0] >= MINUTE:
                    self.sent.popleft()
                if foreground or (
                    len(self.sent) < BACKGROUND_PER_MINUTE and now >= self.quiet_until
                ):
                    self.sent.append(now)
                    return True
                full = self.sent[0] + MINUTE if len(self.sent) >= BACKGROUND_PER_MINUTE else now
                free = max(full, self.quiet_until)
            if now >= deadline:
                return False
            self.pause(max(0.01, min(free, deadline) - now))

    def throttled(self, host: str, retry_after: str | None) -> None:
        """Keep the background quiet for as long as a 429 of a Wikipedia host asks."""
        if not host.endswith(WIKI_HOSTS):
            return
        quiet = float(retry_after) if retry_after and retry_after.isdigit() else QUIET_AFTER_429
        with self.lock:
            self.quiet_until = max(self.quiet_until, self.clock() + quiet)
