"""Перемотка пультом ТВ мимо страницы при «На ТВ» доходит до слушателя (:mod:`web.tv_session`)."""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest

from tests.fakes.receiver import FakeReceiver
from torrcast.domain.position import Position
from web.tv_session import TvSession


def _until(said: Callable[[], bool], limit: float = 2.0) -> None:
    began = time.monotonic()
    while time.monotonic() - began < limit and not said():
        time.sleep(0.01)
    assert said(), "опрос не дошёл до нужного состояния за отведённое время"


def _session(at: float) -> tuple[FakeReceiver, TvSession, list[Position]]:
    receiver = FakeReceiver(Position(at, 7200.0, playing=True, state="PLAYING"))
    session = TvSession(factory=lambda address, profile: receiver, poll_seconds=0.01)
    heard: list[Position] = []
    session.start("192.0.2.104", "t", "u", at, echo=heard.append)
    _until(lambda: bool(heard))
    return receiver, session, heard


@pytest.mark.machine
def test_a_seek_back_from_the_tv_remote_reaches_the_listener_and_the_stop_place() -> None:
    """🔴 Стенд 06-10-2026 до правки: пульт 1681.8 -> 1381.8, слушатель (эхо в упаковку и
    ползунок) не услышал НИ ОДНОГО доклада назад - место залипло на 1678.5, а упаковка
    сочла запрошенное «позади зрителя» и промолчала."""
    receiver, session, heard = _session(1681.8)
    try:
        receiver.current = Position(1381.8, 7200.0, playing=True, state="BUFFERING")
        _until(lambda: any(spot.pos == 1381.8 for spot in heard))
        receiver.current = Position(1385.0, 7200.0, playing=True, state="PLAYING")
        _until(lambda: heard[-1].pos == 1385.0)
    finally:
        at = session.stop()

    assert at == 1385.0, f"«На комп» вернул бы зрителя на старое место: {at}"


@pytest.mark.machine
def test_a_single_report_back_is_still_swallowed_as_a_tail() -> None:
    """Излёт - один доклад назад, следом снова вперёд: слушателю он не уходит."""
    receiver, session, heard = _session(100.0)
    try:
        receiver.current = Position(90.0, 7200.0, playing=True, state="PLAYING")
        _until(lambda: len(receiver.fronts) >= 3)
        receiver.current = Position(80.0, 7200.0, playing=True, state="PLAYING")
        _until(lambda: len(receiver.fronts) >= 6)
        receiver.current = Position(104.0, 7200.0, playing=True, state="PLAYING")
        _until(lambda: heard[-1].pos == 104.0)
    finally:
        session.stop()

    said = [spot.pos for spot in heard]
    assert 90.0 not in said and 80.0 not in said, f"излёт дошёл до слушателя: {said}"
