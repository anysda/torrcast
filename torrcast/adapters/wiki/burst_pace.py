"""Short-window pace of Wikipedia requests: the minute budget does not see a burst."""

import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Final

#: A cold shelf sent 74-120 Wikipedia requests in ten seconds and drew 5-11 429s, well
#: inside the minute budget; dev never went past 32 in ten seconds and saw none.
WINDOW: Final = 10.0
#: Requests per :data:`WINDOW`: under the smallest burst that drew a 429, 1.5 times dev's peak.
MOST: Final = 50


class BurstPace:
    """At most :data:`MOST` requests per :data:`WINDOW`; the rest waits, never past its timeout."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        pause: Callable[[float], None] = time.sleep,
    ) -> None:
        self.clock = clock
        self.pause = pause
        self.sent: deque[float] = deque()
        self.lock = threading.Lock()

    def admit(self, timeout: float) -> bool:
        """Take a slot of the window; ``False`` when none frees within ``timeout``."""
        deadline = self.clock() + timeout
        while True:
            with self.lock:
                now = self.clock()
                while self.sent and now - self.sent[0] >= WINDOW:
                    self.sent.popleft()
                if len(self.sent) < MOST:
                    self.sent.append(now)
                    return True
                free = self.sent[0] + WINDOW
                if free > deadline:
                    return False
            self.pause(max(0.01, free - now))


__all__ = ["MOST", "WINDOW", "BurstPace"]
