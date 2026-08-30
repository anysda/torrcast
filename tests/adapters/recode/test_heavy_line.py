"""Зеркало строки старта кодировщика: она называет ту мерку, по которой куски и взяты."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.adapters.recode.grids import grid, keys
from torrcast.adapters.recode.heavy_line import _heavy_line
from torrcast.adapters.recode.recoder import Recoder
from torrcast.adapters.recode.weights import Weights

if TYPE_CHECKING:
    from pathlib import Path

#: Потолок веса, до которого не дотягивает ни один кусок этой сетки.
ROOMY = 100_000_000
#: Потолок веса, который перешагивает каждый её кусок.
TIGHT = 1_000_000


def _recoder(spare: Path, rate: float, cap: int) -> Recoder:
    lines = grid()
    weights = Weights.of(keys(rate=rate), lines)
    assert weights is not None
    return Recoder(
        source="src", audio=0, grid=lines, spare=spare, weights=weights, threshold=15.0, cap=cap
    )


def test_the_bitrate_measure_is_named_when_it_is_the_one_that_fired(tmp_path: Path) -> None:
    """16 Мбит/с при пороге 15, а вес копии до потолка не дотягивает - названа мерка битрейта."""
    line = _heavy_line(_recoder(tmp_path, rate=2.0e6, cap=ROOMY))

    assert "pieces to recode 30 of 30" in line
    assert "bitrate from 15 Mbit/s" in line
    assert "piece weight" not in line


def test_the_weight_measure_is_named_when_the_bitrate_never_crossed(tmp_path: Path) -> None:
    """🔴 TC-691. Куски взял ВЕС: 4 Мбит/с порога не переходят вовсе, а копия тяжелее
    потолка. Названный тут битрейт уводил разбор в битрейт релиза, где ничего и не было.
    """
    line = _heavy_line(_recoder(tmp_path, rate=0.5e6, cap=TIGHT))

    assert "pieces to recode 30 of 30" in line
    assert "piece weight above 1 MB" in line
    assert "bitrate" not in line


def test_both_measures_are_named_when_both_fired(tmp_path: Path) -> None:
    """Сработали обе мерки - названы обе: разбор не должен гадать, которая решила."""
    line = _heavy_line(_recoder(tmp_path, rate=2.0e6, cap=TIGHT))

    assert "bitrate from 15 Mbit/s and piece weight above 1 MB" in line
