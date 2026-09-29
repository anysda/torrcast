"""One more outcome of an indexer: its run of silence grows, starts over, or ends."""

from __future__ import annotations

from torrcast.domain.is_down import DOWN_WINDOW, Run


def next_run(run: Run | None, *, answered: bool, now: float) -> Run | None:
    """The run after one more outcome: an answer ends it, a stale one starts over."""
    if answered:
        return None
    if run is None or now - run[1] > DOWN_WINDOW:
        return (1, now)
    return (run[0] + 1, now)


__all__ = ["next_run"]
