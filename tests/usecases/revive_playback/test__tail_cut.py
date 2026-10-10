"""Зеркало обрыва на хвосте: когда конец сеанса - обрыв, а когда законный конец."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.usecases.revive_playback.world import feed_with_segments
from torrcast.domain.entry import Entry
from torrcast.usecases.revive_playback._tail_cut import _tail_cut
from torrcast.usecases.watch import Watch

if TYPE_CHECKING:
    from pathlib import Path


def _watch() -> Watch:
    return Watch(key="кино", entry=Entry(title="Кино", magnet="m", dur=7200.0, pos=7190.0))


def test_an_end_without_its_tail_is_cut_short(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """У конца, а кусков до конца нет - сеанс оборван, сторож знает и говорит вслух."""
    watch = _watch()
    assert _tail_cut(watch, feed_with_segments(tmp_path), 7190.0) is True
    assert watch.cut_short is True
    assert "1:59:50" in capsys.readouterr().out


@pytest.mark.parametrize(("slots", "pos"), [(720, 7190.0), (60, 300.0)])
def test_a_served_tail_or_the_middle_is_not_a_cut(tmp_path: Path, slots: int, pos: float) -> None:
    """Хвост отдан - это титры; середина фильма - не вопрос хвоста вовсе."""
    watch = _watch()
    assert _tail_cut(watch, feed_with_segments(tmp_path, slots=slots), pos) is False
    assert watch.cut_short is False and watch.entry.dark == 0.0


def test_no_watch_no_cut(tmp_path: Path) -> None:
    """Сухой показ без сторожа: помечать нечего."""
    assert _tail_cut(None, feed_with_segments(tmp_path), 7190.0) is False
