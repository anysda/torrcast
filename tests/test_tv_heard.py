"""Карточка показа «На ТВ» рисует место и буфер самого ТВ, а не закладку (:mod:`hass.tv_heard`)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tests.fakes.playback_session import FakePlaybackSession
from tests.fakes.receiver import FakeReceiver
from tests.test_bridge import _bridge
from torrcast.adapters.browser.write_web_box import write_web_box
from torrcast.domain.debug_handles import CTL_ENV
from torrcast.domain.json_value import JsonValue
from torrcast.domain.playback_snapshot import PlaybackSnapshot
from torrcast.domain.position import Position
from web.tv_session import SESSION


def _state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tv: Position, box_key: str = "k1"
) -> dict[str, JsonValue]:
    """Снимок моста, пока каст «На ТВ» показа ``k1`` слышит ТВ на ``tv``, а закладка - 15.7."""
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    monkeypatch.setenv(CTL_ENV, str(tmp_path / "torrcast.ctl"))
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Муха", at=0.0, key=box_key)
    monkeypatch.setattr(SESSION, "factory", lambda a, p: FakeReceiver(tv))
    monkeypatch.setattr(SESSION, "poll_seconds", 0.01)
    monkeypatch.setattr(SESSION, "_receiver", None)
    SESSION.start("192.0.2.104", "Муха", "http://x/out.m3u8", 15.7, key="k1")
    shown = PlaybackSnapshot(
        key="movie:муха", title="Муха", position=15.7, duration=7200.0, moved=True
    )
    session = FakePlaybackSession(playing=True, play_key="movie:муха", shown=shown)
    bridge = _bridge(session)
    try:
        began = time.monotonic()
        while SESSION.heard("k1") is None and time.monotonic() - began < 2.0:
            time.sleep(0.01)
        return bridge.state()
    finally:
        SESSION.stop()


@pytest.mark.machine
def test_the_tv_buffer_after_a_seek_is_not_drawn_as_a_running_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Стенд 06-10-2026: +100 от 15.7, ТВ 19 с в буфере на 118.4, а мост звал показ
    ``playing`` по закладке - Home Assistant крутил часы и обогнал ТВ на 14.5 с."""
    body = _state(tmp_path, monkeypatch, Position(118.4, 7200.0, True, "BUFFERING"))

    assert body["state"] == "starting", "буфер ТВ нарисован идущими часами"
    assert body["position"] == 118.4, "место ТВ подменено устаревшей закладкой"
    assert body["title"] == "Муха", "буфер ТВ стёр картину с карточки"


@pytest.mark.machine
def test_a_playing_tv_gives_its_own_place_not_the_ten_second_bookmark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _state(tmp_path, monkeypatch, Position(126.6, 7200.0, True, "PLAYING"))

    assert body["state"] == "playing"
    assert body["position"] == pytest.approx(126.6, abs=0.5), "место ТВ подменено закладкой"


@pytest.mark.machine
def test_a_cast_of_another_tab_show_does_not_speak_for_this_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _state(tmp_path, monkeypatch, Position(126.6, 7200.0, True, "BUFFERING"), "k2")

    assert (body["state"], body["position"]) == ("playing", 15.7)
