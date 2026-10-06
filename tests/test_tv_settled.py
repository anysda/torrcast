"""Доклад назад без своей цели: излёт или перемотка пультом ТВ (:mod:`web.tv_settled`)."""

from __future__ import annotations

from torrcast.domain.position import Position
from web.tv_settled import SETTLE_SECONDS, tv_settled


def _at(pos: float) -> Position:
    return Position(pos, 7200.0, playing=True)


def test_a_seek_from_the_tv_remote_is_heard_once_the_place_settles() -> None:
    """Пульт ТВ мимо страницы: своей цели нет, правда - второй доклад у того же места."""
    first = Position(1381.8, 7200.0, playing=True, state="BUFFERING")
    assert not tv_settled(first, None)
    assert tv_settled(Position(1381.8, 7200.0, playing=True, state="BUFFERING"), first)
    assert tv_settled(Position(1383.8, 7200.0, playing=True, state="PLAYING"), first)


def test_a_lone_tail_and_a_repeated_echo_of_a_playing_receiver_stay_tails() -> None:
    doubt = _at(3.6)
    assert not tv_settled(_at(3.6), doubt), "то же число у играющего - эхо статуса"
    assert not tv_settled(_at(3.0), doubt), "ещё дальше назад - не устоялось"
    assert not tv_settled(_at(3.6 + SETTLE_SECONDS + 1.0), doubt), "ушёл дальше трёх тактов"
