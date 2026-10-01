"""Проверяет стирание отметки последней серии."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.browser.clear_web_last import clear_web_last
from torrcast.adapters.browser.read_web_last import read_web_last
from torrcast.adapters.browser.write_web_last import write_web_last


def test_clearing_an_absent_mark_does_not_raise(tmp_path: Path) -> None:
    clear_web_last(tmp_path)  # без исключения


def test_a_cleared_mark_reads_back_as_no_key(tmp_path: Path) -> None:
    write_web_last(tmp_path, "k1")

    clear_web_last(tmp_path)

    assert read_web_last(tmp_path) == ""
