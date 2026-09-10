"""Проверяет вход позиции от вкладки: ``POST /api/web/position``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fakes.receiver import FakeReceiver
from torrcast.adapters.browser.read_web_position import read_web_position
from torrcast.adapters.browser.write_web_box import write_web_box
from torrcast.adapters.browser.write_web_position import write_web_position
from torrcast.domain.json_value import JsonValue
from torrcast.domain.position import Position
from torrcast.usecases.start_progress import START
from web.position import position
from web.request import Request
from web.tv_session import SESSION


def _post(body: dict[str, JsonValue]) -> Request:
    return Request("POST", "/api/web/position", {}, body)


def test_a_matching_key_is_accepted_and_lands_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="u", title="t", at=0.0, key="k1")

    answer = position(_post({"key": "k1", "pos": 30.0, "dur": 120.0, "phase": "playing"}))

    assert answer.code == 204
    record = read_web_position(tmp_path)
    assert record is not None
    assert record["pos"] == 30.0
    assert record["phase"] == "playing"


def test_a_missing_key_is_refused_as_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="u", title="t", at=0.0, key="k1")

    answer = position(_post({"pos": 30.0, "dur": 120.0, "phase": "playing"}))

    assert answer.code == 409
    assert json.loads(answer.body) == {"error": "stale_key"}


def test_a_stranger_key_from_a_past_session_is_refused_as_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="u", title="t", at=0.0, key="k1")

    answer = position(_post({"key": "old-session", "pos": 30.0, "dur": 120.0, "phase": "playing"}))

    assert answer.code == 409
    assert json.loads(answer.body) == {"error": "stale_key"}


def test_a_word_the_tab_may_not_say_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="u", title="t", at=0.0, key="k1")

    answer = position(_post({"key": "k1", "pos": 30.0, "dur": 120.0, "phase": "flying"}))

    assert answer.code == 400
    assert json.loads(answer.body) == {"error": "bad_phase"}


def test_a_position_that_is_not_a_number_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="u", title="t", at=0.0, key="k1")

    answer = position(_post({"key": "k1", "pos": "далеко", "dur": 120.0, "phase": "playing"}))

    assert answer.code == 400
    assert json.loads(answer.body) == {"error": "bad_number"}


def _casting(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    """Поднять каст на ТВ так, как его поднимает ``/api/to-tv``, но без сети."""
    tv = FakeReceiver(Position(0.0, 0.0))
    monkeypatch.setattr(SESSION, "factory", lambda address, profile: tv)
    monkeypatch.setattr(SESSION, "poll_seconds", 0.01)
    monkeypatch.setattr(SESSION, "_receiver", None)
    SESSION.start("192.168.1.90", "t", "u", 0.0, key=key)


def test_while_the_show_is_on_tv_the_tab_no_longer_moves_the_bookmark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ТЗ §7.5.3: место знает приёмник ТВ, и доклад вкладки принимается, но не пишется."""
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="u", title="t", at=0.0, key="k1")
    write_web_position(tmp_path, key="k1", pos=500.0, dur=8000.0, phase="playing", wall=0.0)
    _casting(monkeypatch, key="k1")
    try:
        answer = position(_post({"key": "k1", "pos": 30.0, "dur": 8000.0, "phase": "playing"}))
    finally:
        SESSION.stop()

    assert answer.code == 204
    record = read_web_position(tmp_path)
    assert record is not None
    assert record["pos"] == 500.0, "вкладка перебила секунду ТВ"


def test_a_stale_key_is_still_refused_while_the_show_is_on_tv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """409 - единственный сигнал вкладке о подмене ящика, и каст его не глушит."""
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="u", title="t", at=0.0, key="k2")
    _casting(monkeypatch, key="k2")
    try:
        answer = position(_post({"key": "k1", "pos": 30.0, "dur": 8000.0, "phase": "playing"}))
    finally:
        SESSION.stop()

    assert answer.code == 409


def test_a_cast_of_another_show_does_not_silence_the_tab(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ящик уехал под новую картину, а ТВ играет прежнюю: место новой пишет вкладка.

    Иначе показ, начатый в браузере поверх живого каста, не двинул бы закладку ни разу и
    навсегда остался бы в ``starting`` - продукт узнаёт о начале показа только отсюда.
    """
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="u", title="t", at=0.0, key="new")
    _casting(monkeypatch, key="old")
    try:
        answer = position(_post({"key": "new", "pos": 30.0, "dur": 8000.0, "phase": "playing"}))
    finally:
        SESSION.stop()

    assert answer.code == 204
    record = read_web_position(tmp_path)
    assert record is not None
    assert record["pos"] == 30.0, "новую картину заперло чужим кастом"


def test_the_first_playing_second_of_the_tab_measures_the_lift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Подъём меряется первой живой секундой ВКЛАДКИ, а не концом команды показа.

    Для человека картинка приходит тогда, когда её показала плёнка; команда показа
    кончается позже, а запись показа узнаёт про кадр ещё позже (живой замер 10-09-2026:
    кадр на 17.0 с, конец команды на 20.5 с, слово ``playing`` в состоянии - на 28.0 с).
    Этим сроком продукт отвечает следующему зрителю, поэтому мерить его надо там, где
    зритель его и прожил.
    """
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="u", title="t", at=0.0, key="k1")
    START.gone()
    START.began()

    position(_post({"key": "k1", "pos": 0.0, "dur": 120.0, "phase": "buffering"}))
    # Плёнка ещё копит ящик: кадра не было, и ожидание остаётся ожиданием.
    assert START.seen() is not None

    position(_post({"key": "k1", "pos": 0.4, "dur": 120.0, "phase": "playing"}))

    assert START.seen() is None, "вкладка играет, а ожидание всё ещё на экране"
