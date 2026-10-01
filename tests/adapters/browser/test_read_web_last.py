"""Проверяет чтение отметки последней серии."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.browser.read_web_last import read_web_last
from torrcast.adapters.browser.web_last_path import web_last_path


def test_nothing_written_reads_back_as_no_key(tmp_path: Path) -> None:
    assert read_web_last(tmp_path) == ""


def test_a_broken_mark_reads_back_as_no_key(tmp_path: Path) -> None:
    web_last_path(tmp_path).write_text("{half", encoding="utf-8")
    assert read_web_last(tmp_path) == ""
