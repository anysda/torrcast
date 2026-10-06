"""Карточка показа «На ТВ» рисует место и буфер самого ТВ, а не закладку (:mod:`hass.tv_heard`)."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hass.record_fresh import FRESH_SECONDS
from hass.say import TOGGLE
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tv: Position,
    box_key: str = "k1",
    wait: float = 2.0,
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
        while SESSION.heard("k1") is None and time.monotonic() - began < wait:
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


@pytest.mark.machine
def test_a_cast_seeked_and_not_heard_yet_is_not_drawn_as_a_running_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Стенд 06-10-2026: -240 со 129.6, мост отдал закладку «playing 0.0», пока ТВ искал
    место, а опрос HA засчитал весь буфер за ход - карточка обогнала ТВ на 4.2 с."""
    monkeypatch.setattr(SESSION, "heard", lambda key: None)  # перемотка обнулила доклад

    body = _state(tmp_path, monkeypatch, Position(0.0, 7200.0, True, "BUFFERING"), wait=0.0)

    assert (body["state"], body["position"]) == ("starting", 15.7)


def _record_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, word: str, age: float, toggled: bool = False
) -> dict[str, JsonValue]:
    """Снимок моста при касте «Play on TV» с карточки: место знает только запись юнита."""
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    monkeypatch.setenv(CTL_ENV, str(tmp_path / "torrcast.ctl"))
    written = (datetime.now(UTC) - timedelta(seconds=age)).astimezone().isoformat()
    shown = PlaybackSnapshot(
        key="movie:муха",
        title="Муха",
        position=737.9,
        duration=7200.0,
        moved=True,
        paused=word,
        updated=written,
    )
    session = FakePlaybackSession(playing=True, play_key="movie:муха", shown=shown)
    bridge = _bridge(session)
    if toggled:  # мост слышал игру, затем пауза с карточки (:mod:`tests.test_bridge`)
        bridge.state()
        bridge.control(TOGGLE, 0.0)
    return bridge.state()


@pytest.mark.machine
def test_a_card_cast_buffering_after_a_remote_seek_is_not_drawn_as_a_running_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Стенд 06-10-2026, «Play on TV» с карточки, пульт «+600»: ТВ 14 с в буфере, а мост
    звал показ ``playing`` - Home Assistant крутил часы над стоящим экраном."""
    body = _record_state(tmp_path, monkeypatch, "BUFFERING", 1.0)

    assert body["state"] == "starting", "буфер ТВ нарисован идущими часами"


@pytest.mark.machine
def test_a_card_cast_record_is_counted_to_now_not_to_its_last_tick(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Стенд 06-10-2026: запись юнита ложится раз в 10 с, и карточка шла на 3-8 с позади ТВ
    (746.9 при 749.8, 476.6 при 484.9). Место идущего показа досчитывается до сейчас."""
    body = _record_state(tmp_path, monkeypatch, "PLAYING", 4.0)

    assert body["state"] == "playing"
    assert body["position"] == pytest.approx(741.9, abs=0.5), "место - на тике записи"


@pytest.mark.machine
def test_a_paused_or_stale_card_cast_record_is_not_counted_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Пауза стоит; запись старше тика с запасом - юнит не пишет, и часы за него не идут."""
    paused = _record_state(tmp_path, monkeypatch, "PAUSED", 4.0)
    stale = _record_state(tmp_path, monkeypatch, "PLAYING", 300.0)

    assert (paused["state"], paused["position"]) == ("paused", 737.9)
    assert stale["position"] == pytest.approx(737.9 + FRESH_SECONDS, abs=0.5)


@pytest.mark.machine
def test_a_card_cast_paused_by_the_bridge_is_not_counted_on_before_the_record_hears_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Пауза с карточки: слово моста - сразу, а запись ещё ``PLAYING`` до круга опроса юнита.
    Досчитай её - ползунок паузы уехал бы вперёд на возраст записи."""
    body = _record_state(tmp_path, monkeypatch, "PLAYING", 4.0, toggled=True)

    assert (body["state"], body["position"]) == ("paused", 737.9)
