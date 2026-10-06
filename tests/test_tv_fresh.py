"""Место ТВ, досчитанное до сейчас: опрос читает статус на прошлую просьбу (:mod:`web.tv_fresh`)."""

from __future__ import annotations

import time

import pytest

from tests.fakes.receiver import FakeReceiver
from torrcast.domain.position import Position
from web.tv_fresh import tv_fresh
from web.tv_session import TvSession

PLAYING = Position(111.9, 7200.0, True, "PLAYING")


def test_a_steady_play_is_counted_from_the_previous_request() -> None:
    """Стенд 06-10-2026: доклад 111.9 при ТВ на 114.6 - статус ответил на просьбу 2 с назад."""
    assert tv_fresh(PLAYING, 10.0, now=12.7).pos == pytest.approx(114.6)


def test_the_count_stops_at_the_end_of_the_film() -> None:
    near_end = Position(7199.0, 7200.0, True, "PLAYING")

    assert tv_fresh(near_end, 0.0, now=5.0).pos == 7200.0


@pytest.mark.machine
def test_the_session_hands_out_the_place_counted_to_now() -> None:
    """Каст «На ТВ» отдаёт карточке место ТВ на миг вопроса, а не на миг прошлого опроса."""
    session = TvSession(factory=lambda a, p: FakeReceiver(PLAYING), poll_seconds=0.05)
    session.start("192.0.2.104", "t", "u", 111.9, key="k1")
    try:
        time.sleep(0.3)
        heard = session.heard("k1")
    finally:
        session.stop()

    assert heard is not None and heard.pos > 111.9, f"доклад отдан на миг опроса: {heard}"
