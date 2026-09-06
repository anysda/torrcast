"""Проверяет запись позиции, присланной вкладкой."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.browser.read_web_position import read_web_position
from torrcast.adapters.browser.write_web_position import write_web_position


def test_the_position_lands_readable_with_its_wall_clock_mark(tmp_path: Path) -> None:
    write_web_position(tmp_path, key="k1", pos=30.0, dur=120.0, phase="playing", wall=1000.0)

    assert read_web_position(tmp_path) == {
        "key": "k1",
        "pos": 30.0,
        "dur": 120.0,
        "phase": "playing",
        "wall": 1000.0,
    }


def test_a_later_write_replaces_the_earlier_one(tmp_path: Path) -> None:
    write_web_position(tmp_path, key="k1", pos=30.0, dur=120.0, phase="playing", wall=1000.0)
    write_web_position(tmp_path, key="k1", pos=40.0, dur=120.0, phase="paused", wall=1010.0)

    record = read_web_position(tmp_path)
    assert record is not None
    assert record["pos"] == 40.0
    assert record["phase"] == "paused"
