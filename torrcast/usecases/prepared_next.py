"""One early search for an episode past the current torrent boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock, Thread
from typing import TYPE_CHECKING

from torrcast.usecases.find_next import find_next

if TYPE_CHECKING:
    from collections.abc import Callable

    from torrcast.domain.config import Config
    from torrcast.domain.entry import Entry
    from torrcast.domain.profile import Profile
    from torrcast.ports.torrent_engine import TorrentEngine
    from torrcast.usecases.select.plan import Plan
    from torrcast.usecases.select_bench.bench import Bench


@dataclass(slots=True)
class PreparedNext:
    """Start only once near the credits and retain its answer until the hand-off."""

    config: Config
    key: str
    torrserver: TorrentEngine
    profile: Profile
    entry: Entry
    target: tuple[int, int]
    circle: Callable[..., list[Plan]]
    stand: Callable[..., Bench]
    _thread: Thread | None = field(default=None, init=False)
    _result: tuple[Entry, int] | None = field(default=None, init=False)
    _lock: Lock = field(default_factory=Lock, init=False)

    def start(self) -> None:
        """Begin the one search without stopping the current receiver poll."""
        with self._lock:
            if self._thread is not None:
                return
            self._thread = Thread(target=self._find, name="next-episode-search", daemon=True)
            self._thread.start()

    def result(self) -> tuple[Entry, int] | None:
        """Return the prepared entry, waiting only if the credits arrived first."""
        self.start()
        assert self._thread is not None
        self._thread.join()
        return self._result

    def _find(self) -> None:
        self._result = find_next(
            self.config,
            self.key,
            self.torrserver,
            self.profile,
            self.entry,
            self.target,
            self.circle,
            self.stand,
        )
