"""Проверяет чтение позиции вкладки со стороны приёмника."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.browser.read_web_position import read_web_position


def test_nothing_written_reads_back_as_none(tmp_path: Path) -> None:
    assert read_web_position(tmp_path) is None
