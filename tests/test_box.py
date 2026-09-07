"""Проверяет почтовый ящик вкладки: ``GET /api/web/box``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fakes.receiver import FakeReceiver
from torrcast.adapters.browser.write_web_box import write_web_box
from torrcast.domain.position import Position
from web.box import box
from web.request import Request
from web.tv_session import SESSION


def _get() -> Request:
    return Request("GET", "/api/web/box", {}, {})


def test_nothing_to_show_answers_an_empty_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))

    answer = box(_get())

    assert answer.code == 200
    assert json.loads(answer.body) == {"tv": False}


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
        "tv": False,
    }


def test_a_live_cast_is_told_to_the_tab_so_it_does_not_play_aloud_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Вкладка, зашедшая уже во время каста, узнаёт про него от продукта, а не из памяти."""
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    tv = FakeReceiver(Position(0.0, 0.0))
    monkeypatch.setattr(SESSION, "factory", lambda address, profile: tv)
    monkeypatch.setattr(SESSION, "poll_seconds", 0.01)
    monkeypatch.setattr(SESSION, "_receiver", None)
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Interstellar", at=12.0, key="k1")
    SESSION.start("192.168.1.90", "Interstellar", "http://x/out.m3u8", 12.0)
    try:
        assert json.loads(box(_get()).body)["tv"] is True
    finally:
        SESSION.stop()
