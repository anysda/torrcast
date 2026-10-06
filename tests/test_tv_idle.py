"""Доклад ТВ без картины места не называет (:func:`web.tv_idle.tv_idle`)."""

from __future__ import annotations

from torrcast.domain.position import Position
from web.tv_idle import tv_idle

IDLE = Position(0.0, 0.0, False, "IDLE")


def test_a_film_played_to_the_end_keeps_its_place_and_says_idle() -> None:
    """Стенд 06-10-2026: фильм доигран до 10143.9, ТВ ушёл в ``IDLE`` с нулём - карточка
    встала на 0.0, а эхо положило ноль в закладку."""
    spot = tv_idle(IDLE, Position(10143.5, 10143.9, True, "PLAYING"), None)

    assert (spot.pos, spot.dur, spot.state, spot.playing) == (10143.5, 10143.9, "IDLE", False)


def test_after_an_own_seek_the_idle_report_stands_at_its_target() -> None:
    """Своя перемотка забывает доклад (:meth:`web.tv_session.TvSession.steer`)."""
    assert tv_idle(IDLE, None, (10143.5, 10138.9)).pos == 10138.9


def test_a_cast_on_its_way_up_and_a_playing_tv_are_left_as_they_are() -> None:
    playing = Position(5.0, 60.0, True, "PLAYING")

    assert tv_idle(IDLE, None, None) == IDLE
    assert tv_idle(playing, Position(4.0, 60.0, True, "PLAYING"), None) == playing
