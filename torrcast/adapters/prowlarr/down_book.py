"""Which indexers keep silent, kept beside the state so a restart does not forget them.

The clients live one search each, and the run of silence is over searches
(:mod:`torrcast.domain.is_down`), so it lives in the process, like Prowlarr's queue
(:mod:`torrcast.adapters.prowlarr.host_slots`), and on disk: every cold start used to wait
the full circle on a source that had been down for hours, and the command and the serve
share what they learned. A file that cannot be read or written is an empty book: the circle
waits as it did before, which is never worse than it was.
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Final

from torrcast.adapters.filesystem.state.state_path import state_path
from torrcast.adapters.filesystem.state.write_atomic import _write_atomic
from torrcast.domain.is_down import Run, is_down
from torrcast.domain.next_run import next_run
from torrcast.domain.torrcast_error import TorrcastError

_NAME: Final = "indexers-down.json"


def _book_path() -> Path:
    return state_path().parent / _NAME


class DownBook:
    """Runs of silence by indexer name; the clock is the wall's, as the file outlives us."""

    def __init__(
        self, path: Callable[[], Path] = _book_path, clock: Callable[[], float] = time.time
    ) -> None:
        self._path = path
        self._clock = clock
        self._lock = threading.Lock()

    def where(self) -> Path:
        """The book's file now: an ask outliving its search tells the book it was sent from."""
        return self._path()

    def hear(self, name: str, *, answered: bool, where: Path | None = None) -> None:
        """One more outcome of ``name``: an answer in time, or a silence."""
        path = where or self._path()
        with self._lock:
            runs = self._read(path)
            run = next_run(runs.get(name), answered=answered, now=self._clock())
            if run == runs.get(name):
                return
            if run is None:
                runs.pop(name, None)
            else:
                runs[name] = run
            with contextlib.suppress(OSError, TorrcastError):
                _write_atomic(path, {key: list(value) for key, value in runs.items()})

    def down(self) -> frozenset[str]:
        """The names down right now."""
        now = self._clock()
        with self._lock:
            return frozenset(
                name for name, run in self._read(self._path()).items() if is_down(run, now)
            )

    @staticmethod
    def _read(path: Path) -> dict[str, Run]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return {
                str(name): (int(run[0]), float(run[1]))
                for name, run in payload.items()
                if isinstance(run, list) and len(run) == 2
            }
        except (OSError, ValueError, TypeError, AttributeError):
            return {}


#: The one book of the process: the clients live one search each.
DOWN_BOOK: Final = DownBook()

__all__ = ["DOWN_BOOK", "DownBook"]
