"""Where the slider of the card counts from, and why that origin never walks back."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def mark_position(
    raw: Any, playing: bool, known: float | None, since: datetime, now: datetime
) -> tuple[float | None, datetime]:
    """Moves the slider's origin with the bookmark itself, not with every answer.

    ``known`` and ``since`` are the bookmark on hand and the moment it was taken; the
    pair comes back moved, and the caller keeps it for the next answer.

    The show writes its bookmark once every ten seconds, the poll asks every five,
    and the card draws `position + (now - position_at)`. Stamping the arrival of
    each answer moved the origin under a bookmark that had not moved, so the
    slider walked forward for five seconds and then fell back to the same place -
    again and again, for the whole show.

    A repeated place is not a new measurement, so the origin stays where it was.
    A place that moved forward moves the origin by exactly as much as the bookmark
    moved, and by no more: that keeps the drawn number continuous across the change,
    because it gains exactly what the bookmark gained. A bookmark that jumped
    further ahead than the wall clock went - a seek forward - takes the origin to
    `now`, which only ever moves the number up.

    The origin is never dragged forward to a floor, and that is the whole of the fix:
    a floor is the one thing that can make the drawn number fall. A show gains less
    than a second of picture per second of wall clock whenever the receiver stalls,
    the origin then lags further behind than any floor allows, and pulling it back up
    subtracts exactly that lag from what the person is reading (measured on the
    stand: a bookmark that gained 4 s over 8 s of wall clock threw the counter back
    by 1.3 s). The lag is not lost either: it is given back the moment the bookmark
    catches up with the drawn number, and every state other than a running show
    re-anchors the origin outright - a card that is not playing does not tick, so
    nothing falls back there.
    """
    place = None if raw is None else float(raw)
    if place is None or not playing or known is None or place < known:
        return place, now
    if place == known:
        return known, since
    moved = timedelta(seconds=place - known)
    return place, min(now, since + moved)
