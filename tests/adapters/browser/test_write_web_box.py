"""Проверяет запись задания вкладке."""

import json
from pathlib import Path

from torrcast.adapters.browser.web_box_path import web_box_path
from torrcast.adapters.browser.write_web_box import write_web_box


def test_the_task_lands_readable_on_disk(tmp_path: Path) -> None:
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Interstellar", at=120.0, key="k1")

    written = json.loads(web_box_path(tmp_path).read_text(encoding="utf-8"))
    assert written == {
        "url": "http://x/out.m3u8",
        "title": "Interstellar",
        "at": 120.0,
        "key": "k1",
    }


def test_a_missing_directory_is_made_and_does_not_kill_the_show(tmp_path: Path) -> None:
    out = tmp_path / "нет-такого"
    write_web_box(out, url="u", title="t", at=0.0, key="k")  # без исключения

    assert web_box_path(out).exists()
