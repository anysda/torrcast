"""Проверяет снятие задания вкладке."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.browser.clear_web_box import clear_web_box
from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.adapters.browser.write_web_box import write_web_box


def test_clearing_an_absent_task_does_not_raise(tmp_path: Path) -> None:
    clear_web_box(tmp_path)  # без исключения


def test_a_cleared_task_reads_back_empty(tmp_path: Path) -> None:
    write_web_box(tmp_path, url="u", title="t", at=0.0, key="k")

    clear_web_box(tmp_path)

    assert read_web_box(tmp_path) == {}
