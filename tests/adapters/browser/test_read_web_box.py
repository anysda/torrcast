"""Проверяет чтение задания вкладке со стороны страницы."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.adapters.browser.write_web_box import write_web_box


def test_nothing_written_reads_back_as_an_empty_object_not_none(tmp_path: Path) -> None:
    assert read_web_box(tmp_path) == {}


def test_a_written_task_reads_back_whole(tmp_path: Path) -> None:
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Interstellar", at=12.0, key="k1")

    assert read_web_box(tmp_path) == {
        "url": "http://x/out.m3u8",
        "title": "Interstellar",
        "at": 12.0,
        "key": "k1",
    }
