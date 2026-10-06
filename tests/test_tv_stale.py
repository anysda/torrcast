"""Доклад назад посреди каста: излёт глотается, приезд своей перемотки назад проходит."""

from __future__ import annotations

from torrcast.domain.position import Position
from web.tv_stale import tv_stale


def _at(pos: float) -> Position:
    return Position(pos, 7200.0, playing=True)


def test_a_report_behind_the_last_one_is_a_tail_without_a_seek() -> None:
    assert tv_stale(_at(3.6), _at(5.4), None) == (True, None)
    assert tv_stale(_at(6.0), _at(5.4), None) == (False, None)


def test_the_report_at_the_target_of_a_seek_back_passes_and_ends_the_wait() -> None:
    """TC-1169: первое чтение после команды было старым местом и снова стало «прежним»."""
    aim = (1062.0, 762.0)
    assert tv_stale(_at(1062.0), None, aim) == (False, aim)
    assert tv_stale(_at(745.1), _at(1062.0), aim) == (False, None)


def test_after_the_seek_arrived_a_tail_is_a_tail_again() -> None:
    assert tv_stale(_at(740.0), _at(745.1), None) == (True, None)


def test_a_report_still_near_the_old_place_keeps_waiting() -> None:
    aim = (1062.0, 762.0)
    assert tv_stale(_at(1060.0), _at(1062.0), aim) == (True, aim)
