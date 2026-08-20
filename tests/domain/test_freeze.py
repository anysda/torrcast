"""Зеркало подгруза: потерянная плёнка и длина по стене - разные числа."""

from __future__ import annotations

from torrcast.domain.freeze import Freeze


def test_the_lost_film_and_the_wall_length_are_two_different_numbers() -> None:
    """Простоял зритель ``lost``, а стена подгруза длиннее: в неё входит опрос выхода."""
    stalled = Freeze(pos=163.9, lost=7.4, secs=8.1, total=12.6)

    assert (stalled.lost, stalled.secs) == (7.4, 8.1)
    assert stalled.total >= stalled.lost, "за показ теряется не меньше, чем в одном подгрузе"
