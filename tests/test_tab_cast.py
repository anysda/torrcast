"""Пульт каста «На ТВ»: пауза и перемотка с вкладки идут телевизору (:mod:`hass.tab_cast`)."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from hass.refused_error import NOTHING_PLAYING, RefusedError
from hass.tab_cast import tab_cast
from hass.tab_finish import tab_finish
from tests.fakes.receiver import FakeReceiver
from torrcast.adapters.browser.read_web_finish import read_web_finish
from torrcast.adapters.browser.write_web_box import write_web_box
from torrcast.domain.config import Config
from torrcast.domain.position import Position
from web.tv_session import SESSION, TvSession


@dataclass
class _Steered(FakeReceiver):
    """Приёмник ТВ, который умеет пульт, и запись того, что ему велели."""

    said: list[tuple[str, float]] = field(default_factory=list)

    def seek(self, pos: float) -> None:
        self.said.append(("seek", pos))
        self.current = Position(pos, self.current.dur, self.current.playing)

    def pause(self) -> None:
        self.said.append(("pause", 0.0))

    def resume(self) -> None:
        self.said.append(("resume", 0.0))


def _until(said: Callable[[], bool], limit: float = 2.0) -> None:
    """Ждать доклада опроса, а не спать наугад: такт опроса тут 0.01 с."""
    began = time.monotonic()
    while time.monotonic() - began < limit and not said():
        time.sleep(0.01)
    assert said(), "опрос не дошёл до нужного состояния за отведённое время"


@pytest.fixture
def cast_of(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[_Steered, Config]]:
    """Вкладка играет показ ``k1`` и отдала его «На ТВ»; опрос приёмника стоит."""
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Муха", at=0.0, key="k1")
    receiver = _Steered(Position(600.0, 7200.0, playing=True))
    monkeypatch.setattr(SESSION, "factory", lambda address, profile: receiver)
    monkeypatch.setattr(SESSION, "poll_seconds", 3600.0)
    monkeypatch.setattr(SESSION, "_receiver", None)
    SESSION.start("10.0.1.7", "Муха", "http://x/out.m3u8", 600.0, key="k1")
    yield receiver, Config()
    SESSION.stop()


def test_seekby_on_a_cast_tab_moves_the_tv_from_where_it_stands(
    cast_of: tuple[_Steered, Config],
) -> None:
    """🔴 Показ во вкладке, отданный «На ТВ»: минута назад и вперёд двигает ТЕЛЕВИЗОР.
    Раньше сторож TC-1210 отвечал на это ``no_remote`` - вкладка-де пульта не берёт."""
    receiver, config = cast_of

    assert tab_cast(config, "seekby", -60.0)
    assert tab_cast(config, "seekby", 60.0)

    assert receiver.said == [("seek", 540.0), ("seek", 600.0)]


def test_a_cast_tab_keeps_next_on_the_tv_path(
    cast_of: tuple[_Steered, Config], tmp_path: Path
) -> None:
    """TC-1062 не подменяет Chromecast-вариант вкладочным каналом конца серии."""
    _receiver, config = cast_of

    assert not tab_finish(config, 7199.0)
    assert read_web_finish(tmp_path) == {}


def test_toggle_on_a_cast_tab_pauses_a_playing_tv_and_resumes_a_paused_one(
    cast_of: tuple[_Steered, Config],
) -> None:
    receiver, config = cast_of

    assert tab_cast(config, "toggle", 0.0)
    receiver.current = Position(600.0, 7200.0, playing=False)
    assert tab_cast(config, "toggle", 0.0)

    assert receiver.said == [("pause", 0.0), ("resume", 0.0)]


def test_a_cast_of_another_show_does_not_take_the_command(
    tmp_path: Path, cast_of: tuple[_Steered, Config]
) -> None:
    """Ящик уехал под другой показ - старый каст не его, команда остаётся сторожу TC-1210."""
    receiver, config = cast_of
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Другое", at=0.0, key="k2")

    assert not tab_cast(config, "seekby", 60.0)
    assert receiver.said == []


def test_no_cast_does_not_take_the_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Муха", at=0.0, key="k1")
    monkeypatch.setattr(SESSION, "_receiver", None)

    assert not tab_cast(Config(), "toggle", 0.0)


def test_a_receiver_without_a_remote_leaves_the_command_to_the_refusal() -> None:
    session = TvSession(factory=lambda address, profile: FakeReceiver(Position(5.0, 60.0)))
    session.poll_seconds = 3600.0
    session.start("10.0.1.7", "t", "u", 0.0, key="k1")

    assert not session.steer("seekby", 60.0)
    session.stop()


@dataclass
class _Lagging(_Steered):
    """Приёмник, который берёт перемотку не сразу: чтения ещё отдают старое место."""

    def seek(self, pos: float) -> None:
        self.said.append(("seek", pos))


def test_a_stale_read_right_after_seeking_back_does_not_swallow_the_report_at_the_target() -> None:
    """🔴 TC-1169. Первое чтение после ``steer`` бывает старым местом: оно становилось
    «прежним» докладом, и доклад у цели глотался как излёт - вкладка и ползунок стояли на
    старом месте, пока ТВ играл новое."""
    receiver = _Lagging(Position(1062.0, 7200.0, playing=True))
    heard: list[float] = []
    session = TvSession(factory=lambda address, profile: receiver, poll_seconds=0.01)
    session.start("10.0.1.7", "t", "u", 1062.0, echo=lambda spot: heard.append(spot.pos))
    try:
        _until(lambda: bool(heard))
        assert session.steer("seekby", -300.0)
        asked = len(receiver.fronts)
        _until(lambda: len(receiver.fronts) >= asked + 3)
        receiver.current = Position(762.0, 7200.0, playing=True)
        _until(lambda: 762.0 in heard)
    finally:
        session.stop()

    assert receiver.said == [("seek", 762.0)]


def test_after_seeking_back_the_next_report_is_heard_not_read_as_a_stale_tail() -> None:
    """🔴 Опрос глотает доклад назад как излёт (:meth:`TvSession._backwards`). Своя
    перемотка назад обязана это снять, иначе место ТВ (а за ним плёнка вкладки и закладка)
    стояло бы на старом числе минуту, пока показ его не догонит."""
    receiver = _Steered(Position(600.0, 7200.0, playing=True))
    heard: list[float] = []
    session = TvSession(factory=lambda address, profile: receiver, poll_seconds=0.01)
    session.start("10.0.1.7", "t", "u", 600.0, echo=lambda spot: heard.append(spot.pos))
    try:
        _until(lambda: bool(heard))
        assert session.steer("seekby", -60.0)
        heard.clear()
        _until(lambda: bool(heard))
    finally:
        session.stop()

    assert heard and heard[0] == 540.0


def test_a_tv_that_played_the_film_to_the_end_refuses_the_remote_and_keeps_the_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Стенд 06-10-2026: после конца фильма ТВ в ``IDLE`` с нулём, «+600» отвечали 204, а
    карточка рисовала 0.0, 600 и 1200 при пустом экране."""
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Муха", at=0.0, key="k1")
    receiver = _Steered(Position(7199.0, 7200.0, True, "PLAYING"))
    echoed: list[Position] = []
    session = TvSession(factory=lambda address, profile: receiver, poll_seconds=0.01)
    monkeypatch.setattr("hass.tab_cast.SESSION", session)
    session.start("10.0.1.7", "Муха", "u", 7199.0, echo=echoed.append, key="k1")
    try:
        _until(lambda: len(echoed) >= 3)  # игра установилась: доклад досчитывается
        receiver.current = Position(0.0, 0.0, False, "IDLE")
        asked = len(receiver.fronts)
        _until(lambda: len(receiver.fronts) >= asked + 3)
        with pytest.raises(RefusedError) as refused:
            tab_cast(Config(), "seekby", 600.0)
    finally:
        session.stop()

    assert refused.value.word == NOTHING_PLAYING
    assert receiver.said == [], "команда ушла ТВ без картины"
    # Место - доклад, досчитанный до сейчас (:func:`web.tv_fresh.tv_fresh`): сырой отстаёт
    # на такт опроса, и после конца фильма карточка вставала на 10141.0 из 10143.9.
    assert 7199.0 < echoed[-1].pos <= 7200.0, f"ТВ без картины не на доигранном: {echoed[-1]}"
