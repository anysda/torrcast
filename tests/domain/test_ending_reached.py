"""Зеркало :mod:`torrcast.domain.ending_reached`."""

from __future__ import annotations

from torrcast.domain.ending_reached import ending_reached
from torrcast.domain.entry import ENDING_RATIO

#: Длина того самого фильма из замера: 2:46:55.
WHOLE = 10015.0


def test_a_source_that_died_under_the_show_is_not_the_credits() -> None:
    """Ноль декодера на пятой минуте - это оборванный источник, а не доигранный фильм."""
    assert not ending_reached(282.0, WHOLE)


def test_the_credits_are_the_measured_share_of_the_film() -> None:
    """Мерка та же, по которой показ отличает титры от аварии."""
    assert ending_reached(WHOLE * ENDING_RATIO, WHOLE)
    assert not ending_reached(WHOLE * ENDING_RATIO - 1.0, WHOLE)


def test_an_unknown_length_leaves_the_old_rule_in_place() -> None:
    """Длину фильма приёмник знает не всегда: судить не по чему - конец есть конец."""
    assert ending_reached(282.0, 0.0)
