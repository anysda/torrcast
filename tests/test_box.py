"""Проверяет почтовый ящик вкладки: ``GET /api/web/box``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from torrcast.adapters.browser.write_web_box import write_web_box
from web.box import box
from web.request import Request


def _get() -> Request:
    return Request("GET", "/api/web/box", {}, {})


def test_nothing_to_show_answers_an_empty_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))

    answer = box(_get())

    assert answer.code == 200
    assert json.loads(answer.body) == {}


def test_a_pending_task_is_handed_to_the_tab(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Interstellar", at=12.0, key="k1")

    answer = box(_get())

    assert json.loads(answer.body) == {
        "url": "http://x/out.m3u8",
        "title": "Interstellar",
        "at": 12.0,
        "key": "k1",
    }
