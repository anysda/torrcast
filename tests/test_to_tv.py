"""Проверяет каст идущего показа на ТВ: ``POST /api/to-tv``."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.fakes.receiver import FakeReceiver
from torrcast.adapters.browser.write_web_box import write_web_box
from torrcast.adapters.browser.write_web_position import write_web_position
from torrcast.domain.config import Config
from torrcast.domain.position import Position
from web.request import Request
from web.to_tv import to_tv
from web.tv_session import SESSION


def _post() -> Request:
    return Request("POST", "/api/to-tv", {}, {})


def _wired(monkeypatch: pytest.MonkeyPatch, tv: str = "192.168.1.104") -> FakeReceiver:
    monkeypatch.setattr("web.to_tv.load_config", lambda: Config(tv=tv))
    receiver = FakeReceiver(Position(0.0, 0.0))
    monkeypatch.setattr(SESSION, "factory", lambda address, profile: receiver)
    monkeypatch.setattr(SESSION, "poll_seconds", 0.01)
    monkeypatch.setattr(SESSION, "_receiver", None)
    return receiver


@pytest.fixture(autouse=True)
def _stop_any_cast_left_running() -> Iterator[None]:
    """Убирает опрос, если тест поднял каст и не снял его: без этого фоновый поток
    держателя (:mod:`web.tv_session`) жил бы до конца всего прогона тестов."""
    yield
    SESSION.stop()


def test_no_configured_tv_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    _wired(monkeypatch, tv="")

    answer = to_tv(_post())

    assert answer.code == 409
    assert json.loads(answer.body) == {"error": "no_tv"}


def test_nothing_playing_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    _wired(monkeypatch)

    answer = to_tv(_post())

    assert answer.code == 409
    assert json.loads(answer.body) == {"error": "nothing_playing"}


def test_the_running_show_is_cast_without_restarting_the_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    receiver = _wired(monkeypatch)
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Interstellar", at=12.0, key="k1")
    write_web_position(tmp_path, key="k1", pos=88.0, dur=8000.0, phase="playing", wall=0.0)

    answer = to_tv(_post())

    assert answer.code == 204
    assert receiver.plays == [("http://x/out.m3u8", "Interstellar", 88.0)]


def test_a_stale_mailbox_position_is_ignored_for_a_fresh_box(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    receiver = _wired(monkeypatch)
    write_web_position(
        tmp_path, key="old-session", pos=999.0, dur=8000.0, phase="playing", wall=0.0
    )
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Interstellar", at=5.0, key="k1")

    answer = to_tv(_post())

    assert answer.code == 204
    assert receiver.plays == [("http://x/out.m3u8", "Interstellar", 5.0)]
