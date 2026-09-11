"""Проверяет держатель одной живой связи с приёмником ТВ (:mod:`web.tv_session`)."""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest

from tests.fakes.receiver import FakeReceiver
from torrcast.domain.position import Position
from torrcast.domain.profile import ANDROID_TV, CAUTIOUS, Profile
from web.tv_session import TvSession


def _until(said: Callable[[], bool], limit: float = 2.0) -> None:
    """Ждать события опроса, а не спать наугад: такт опроса тут 0.01 с."""
    began = time.monotonic()
    while time.monotonic() - began < limit and not said():
        time.sleep(0.01)
    assert said(), "опрос не дошёл до нужного состояния за отведённое время"


def test_start_calls_play_with_the_given_url_title_and_position() -> None:
    receiver = FakeReceiver(Position(0.0, 0.0))
    session = TvSession(factory=lambda address, profile: receiver, poll_seconds=0.01)

    session.start("192.168.1.104", "Interstellar", "http://x/out.m3u8", 42.0)

    assert receiver.plays == [("http://x/out.m3u8", "Interstellar", 42.0)]
    assert session.active()

    session.stop()


def test_start_calls_the_tv_with_the_given_profile_and_the_cautious_one_without() -> None:
    """Профиль LOAD - тот, которым упакован показ; без него - осторожное умолчание."""
    given: list[Profile] = []

    def made(address: str, profile: Profile) -> FakeReceiver:
        given.append(profile)
        return FakeReceiver(Position(0.0, 0.0))

    session = TvSession(factory=made, poll_seconds=0.01)
    session.start("192.168.1.90", "t", "u", 0.0, profile=ANDROID_TV)
    session.start("192.168.1.90", "t", "u", 0.0)
    session.stop()

    assert given == [ANDROID_TV, CAUTIOUS]


def test_stop_reads_the_position_before_stopping_and_forgets_the_receiver() -> None:
    receiver = FakeReceiver(Position(88.0, 120.0))
    session = TvSession(factory=lambda address, profile: receiver, poll_seconds=0.01)
    session.start("192.168.1.104", "t", "u", 0.0)

    at = session.stop()

    assert at == 88.0
    assert receiver.stops == [True]
    assert not session.active()


@pytest.mark.machine
def test_stop_answers_with_the_last_polled_position_not_a_stale_reread() -> None:
    """Чтение на излёте бывает СТАРШЕ последнего доклада опроса (замер на стенде `.104`
    10-09-2026: приставка на стопе отдала 4.8 с там, где опрос секунду назад слышал ~14).
    Ответ «на какой секунде стоял каст» - последний услышанный доклад."""
    receiver = FakeReceiver(Position(0.0, 120.0))
    session = TvSession(factory=lambda address, profile: receiver, poll_seconds=0.01)
    session.start("192.168.1.104", "t", "u", 0.0)
    for _ in range(200):
        if receiver.fronts:
            break
        time.sleep(0.01)
    receiver.current = Position(14.0, 120.0)  # очередной доклад опроса
    for _ in range(200):
        if len(receiver.fronts) >= 2:
            break
        time.sleep(0.01)
    receiver.current = Position(4.8, 120.0)  # чтение на излёте отвечает старьём

    at = session.stop()

    assert at == 14.0


def test_settle_keeps_the_cast_that_belongs_to_the_asked_box() -> None:
    receiver = FakeReceiver(Position(0.0, 0.0))
    session = TvSession(factory=lambda address, profile: receiver, poll_seconds=0.01)
    session.start("192.168.1.90", "t", "u", 0.0, key="k1")

    assert session.settle("k1") is True
    assert session.active()

    session.stop()


def test_settle_takes_down_a_cast_whose_show_is_gone() -> None:
    """Ящик уехал под другую картину - каст первой снимается, а не живёт вечно."""
    receiver = FakeReceiver(Position(0.0, 0.0))
    session = TvSession(factory=lambda address, profile: receiver, poll_seconds=0.01)
    session.start("192.168.1.90", "t", "u", 0.0, key="k1")

    assert session.settle("k2") is False
    assert receiver.stops == [True]
    assert not session.active()


def test_settle_without_a_cast_says_no_and_touches_nothing() -> None:
    assert TvSession().settle("k1") is False


def test_stop_without_a_cast_is_a_harmless_zero() -> None:
    session = TvSession()

    assert session.stop() == 0.0


def test_starting_again_releases_the_previous_connection_first() -> None:
    first = FakeReceiver(Position(0.0, 0.0))
    second = FakeReceiver(Position(0.0, 0.0))
    receivers = iter([first, second])
    session = TvSession(factory=lambda address, profile: next(receivers), poll_seconds=0.01)

    session.start("192.168.1.104", "t", "u1", 0.0)
    session.start("192.168.1.104", "t", "u2", 10.0)

    assert first.stops == [True]
    assert second.plays == [("u2", "t", 10.0)]

    session.stop()


@pytest.mark.machine
def test_the_live_cast_is_polled_periodically_so_the_position_stays_fresh() -> None:
    """Без опроса ``current_time`` у pychromecast застревает на месте первой картинки
    (замерено на стенде ``.104``, см. докстроку :data:`web.live_receiver.POLL_SECONDS`)."""
    receiver = FakeReceiver(Position(0.0, 120.0))
    session = TvSession(factory=lambda address, profile: receiver, poll_seconds=0.01)
    heard: list[Position] = []

    session.start("192.168.1.104", "t", "u", 0.0, echo=heard.append)

    for _ in range(200):
        if receiver.fronts:
            break
        time.sleep(0.01)
    assert receiver.fronts, "опрос не пришёл за 2 секунды"
    # Тот же опрос отдаёт место слушателю: пока каст идёт, других источников секунды нет
    # (ТЗ §7.5.3, :func:`web.to_tv._echo`).
    assert heard, "опрос был, а слушатель места о нём не узнал"

    session.stop()


@pytest.mark.machine
def test_the_cast_is_taken_down_once_its_show_is_gone_and_is_not_asked_again() -> None:
    """Опрос места у ТВ с погасшим потоком поднимал LOAD заново («retrying LOAD»,
    «reloading»; стенд `.104` 11-09-2026): показ снят - каст снимается, ТВ не спрашивается."""
    receiver = FakeReceiver(Position(10.0, 120.0))
    session = TvSession(factory=lambda address, profile: receiver, poll_seconds=0.01)
    alive = [True]
    session.start("192.168.1.90", "t", "u", 0.0, key="k1", alive=lambda: alive[0])
    _until(lambda: bool(receiver.fronts))

    alive[0] = False
    _until(lambda: receiver.stops == [True])
    asked = len(receiver.fronts)
    time.sleep(0.1)

    assert not session.active()
    assert len(receiver.fronts) == asked, "снятый каст всё ещё опрашивается"
    assert session.stop() == 0.0


@pytest.mark.machine
def test_a_report_that_steps_backwards_never_reaches_the_listener() -> None:
    """Приёмник на прогреве отдаёт место рывком назад (стенд `.104` 10-09-2026: 5.4,
    следом 3.6), и вкладка, ведущая свою плёнку по этому числу, прыгала с 15.9 на 4.5.
    Назад секунда каста не ходит: меньший доклад - излёт, и слушателю он не уходит."""
    receiver = FakeReceiver(Position(5.4, 120.0))
    session = TvSession(factory=lambda address, profile: receiver, poll_seconds=0.01)
    heard: list[Position] = []

    session.start("192.168.1.104", "t", "u", 0.0, echo=heard.append)
    _until(lambda: bool(heard))
    receiver.current = Position(3.6, 120.0)
    _until(lambda: len(receiver.fronts) >= 4)
    receiver.current = Position(13.6, 120.0)
    _until(lambda: any(spot.pos == 13.6 for spot in heard))
    session.stop()

    said = [spot.pos for spot in heard]
    assert 3.6 not in said, f"доклад назад дошёл до вкладки: {said}"
    assert said == sorted(said), f"место каста ушло назад: {said}"
