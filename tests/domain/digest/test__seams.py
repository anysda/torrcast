"""Зеркало :mod:`torrcast.domain.digest._seams`: стык источника - это СМЕНА, а не кусок.

Стыки читают затем, что ребуфер на границе прогретого и упакованного - отдельная болезнь
показа. Посчитай правило сами куски - и ровный показ обвинялся бы в сотнях стыков.
"""

from __future__ import annotations

from tests.domain.digest.rows import rec
from torrcast.domain.digest._seams import _seams
from torrcast.domain.trace_sources import PACKED, WARMED


def test_only_the_change_of_source_counts_and_never_the_first_piece() -> None:
    """У первого куска предыдущего источника нет - и стыком он не является."""
    rows = [rec("segment", slot=1, src=WARMED), rec("segment", slot=2, src=PACKED)]

    assert [r["slot"] for r in _seams(rows)] == [2]
    assert _seams(rows[:1]) == [], "показ, начавшийся с прогретого, стыка не даёт"


def test_a_steady_source_gives_no_seams_at_all() -> None:
    """Источник не менялся - говорить не о чем."""
    rows = [rec("segment", slot=n, src=PACKED) for n in range(5)]

    assert _seams(rows) == []


def test_a_segment_without_a_named_source_is_not_a_seam_either() -> None:
    """Записи прежних версий поля источника не носят - выдумывать смену по ним нельзя."""
    rows = [rec("segment", slot=1, src=PACKED), rec("segment", slot=2), rec("segment", slot=3)]

    assert _seams(rows) == []


def test_events_that_are_not_segments_never_make_a_seam() -> None:
    """Стык - про куски: ребуфер между ними источник не меняет."""
    rows = [
        rec("segment", slot=1, src=PACKED),
        rec("buffering"),
        rec("segment", slot=2, src=PACKED),
    ]

    assert _seams(rows) == []
