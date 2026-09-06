"""Проверяет снятие записи позиции прошлого сеанса."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.browser.clear_web_position import clear_web_position
from torrcast.adapters.browser.read_web_position import read_web_position
from torrcast.adapters.browser.write_web_position import write_web_position


def test_clearing_an_absent_record_does_not_raise(tmp_path: Path) -> None:
    clear_web_position(tmp_path)  # без исключения


def test_a_cleared_record_reads_back_as_none(tmp_path: Path) -> None:
    write_web_position(tmp_path, key="k1", pos=1.0, dur=2.0, phase="playing", wall=0.0)

    clear_web_position(tmp_path)

    assert read_web_position(tmp_path) is None
