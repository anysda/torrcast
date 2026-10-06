"""Зеркало :mod:`torrcast.domain.seek_place`: место перемотки внутри картины."""

from __future__ import annotations

from torrcast.domain.seek_place import END_MARGIN, seek_place

_DURATION = 7200.0


def test_the_place_is_cut_at_both_ends_and_left_alone_without_a_length() -> None:
    assert seek_place(100.0, -240.0, _DURATION) == 0.0
    assert seek_place(7000.0, 600.0, _DURATION) == _DURATION - END_MARGIN
    assert seek_place(7000.0, 600.0, 0.0) == 7600.0
    # Вперёд из самого хвоста показ назад не уезжает.
    assert seek_place(_DURATION - 2.0, 60.0, _DURATION) == _DURATION - 2.0
