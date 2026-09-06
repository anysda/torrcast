"""Проверяет возврат идущего показа с ТВ в браузер: ``POST /api/to-web``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fakes.receiver import FakeReceiver
from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.adapters.browser.write_web_box import write_web_box
from torrcast.domain.config import Config
from torrcast.domain.position import Position
from web.request import Request
from web.to_web import to_web
from web.tv_session import SESSION


def _post() -> Request:
    return Request("POST", "/api/to-web", {}, {})


def _wired(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("web.to_web.load_config", lambda: Config())


def test_nothing_casting_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    _wired(monkeypatch)
    monkeypatch.setattr(SESSION, "_receiver", None)

    answer = to_web(_post())

    assert answer.code == 409
    assert json.loads(answer.body) == {"error": "not_casting"}


def test_the_tv_position_becomes_the_new_box_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    _wired(monkeypatch)
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Interstellar", at=12.0, key="k1")
    receiver = FakeReceiver(Position(101.0, 8000.0))
    monkeypatch.setattr(SESSION, "_receiver", receiver)

    answer = to_web(_post())

    assert answer.code == 204
    assert receiver.stops == [True]
    box = read_web_box(tmp_path)
    assert box is not None
    assert box["at"] == 101.0
    assert box["url"] == "http://x/out.m3u8"
    assert box["title"] == "Interstellar"
    assert box["key"] == "k1"


def test_an_emptied_box_is_not_recreated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    _wired(monkeypatch)
    receiver = FakeReceiver(Position(55.0, 8000.0))
    monkeypatch.setattr(SESSION, "_receiver", receiver)

    answer = to_web(_post())

    assert answer.code == 204
    assert read_web_box(tmp_path) == {}
