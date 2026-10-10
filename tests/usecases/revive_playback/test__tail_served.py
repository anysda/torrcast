"""Зеркало вопроса «отдан ли хвост»: куски от места показа до конца картины подряд."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.revive_playback.world import feed_with_segments
from torrcast.usecases.revive_playback._tail_served import _tail_served

if TYPE_CHECKING:
    from pathlib import Path


def test_a_packed_tail_is_served_and_a_hole_before_the_end_is_not(tmp_path: Path) -> None:
    """Сетка 2702.7 с: 270 кусков, последний 12.7 с. Все лежат - отдан; нет последнего - нет."""
    feed = feed_with_segments(tmp_path, slots=270, whole=2702.688)
    assert _tail_served(feed, 2579.5) is True
    (feed.out / "v269.ts").unlink()
    assert _tail_served(feed, 2579.5) is False, "дыра на последнем куске - не конец"


def test_a_place_without_its_own_piece_is_not_served(tmp_path: Path) -> None:
    """Под местом показа куска нет вовсе - отдавать нечего, сколько бы ни лежало дальше."""
    feed = feed_with_segments(tmp_path, slots=60, whole=7200.0)
    assert _tail_served(feed, 7190.0) is False


def test_an_unknown_length_is_never_a_served_tail(tmp_path: Path) -> None:
    """Длины нет - судить о конце не по чему (как и :func:`ending_reached`)."""
    feed = feed_with_segments(tmp_path, slots=1, whole=0.0)
    assert _tail_served(feed, 0.0) is False
