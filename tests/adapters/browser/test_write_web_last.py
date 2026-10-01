"""Проверяет запись отметки последней серии."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.browser.read_web_last import read_web_last
from torrcast.adapters.browser.write_web_last import write_web_last


def test_the_written_key_reads_back(tmp_path: Path) -> None:
    write_web_last(tmp_path, "k1")
    assert read_web_last(tmp_path) == "k1"


def test_a_later_show_replaces_the_earlier_mark(tmp_path: Path) -> None:
    write_web_last(tmp_path, "k1")
    write_web_last(tmp_path, "k2")
    assert read_web_last(tmp_path) == "k2"
