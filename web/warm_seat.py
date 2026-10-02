"""The seat of a warmup circle: the viewer who takes it over gets what it handed its watchers.

A viewer's own circle calls his hook as each client is built (the poster verdict of the
blocking search, the progressive preview). A warmup circle he took over was counted without
it: on the stand, with Knaben silent, his «Terminator» answered 0.4-0.9 s after its circle
against 0.1-0.2 s for a tile the warmup had not taken, as the verdict began on the list.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

from torrcast.adapters.prowlarr.warmup import TAKEN

if TYPE_CHECKING:
    from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient

#: The hook of a circle: called once per client built (``on_indexer``).
Watch = Callable[["IndexerClient"], None]
#: The hook of the viewer who is asking, for a warmup circle he may take over.
_WATCH: ContextVar[Watch | None] = ContextVar("watch", default=None)


class WarmSeat(threading.Event):
    """Set once a viewer took the circle; his hook gets every client, built before or after."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._built: list[IndexerClient] = []
        self._watch: Watch | None = None

    @staticmethod
    @contextmanager
    def watching(watch: Watch) -> Iterator[None]:
        """The asks in this block hand ``watch`` to a warmup circle they take over."""
        token = _WATCH.set(watch)
        try:
            yield
        finally:
            _WATCH.reset(token)

    @staticmethod
    def relay(client: IndexerClient) -> None:
        """The warmup circle's ``on_indexer``: hand the client to the seat it is counted for."""
        seat = TAKEN.get()
        if isinstance(seat, WarmSeat):
            seat._landed(client)

    def take(self) -> None:
        """The asking viewer's circle from now on: his hook (:meth:`watching`) gets its clients."""
        watch = _WATCH.get()
        with self._lock:
            self._watch = watch
            built = list(self._built)
        self.set()
        if watch is not None:
            for client in built:
                watch(client)

    def _landed(self, client: IndexerClient) -> None:
        with self._lock:
            self._built.append(client)
            watch = self._watch
        if watch is not None:
            watch(client)


__all__ = ["WarmSeat"]
