"""С какого мига верен доклад ТВ (:mod:`web.tv_since`)."""

from __future__ import annotations

from torrcast.domain.position import Position
from web.tv_since import tv_since

PLAYING = Position(111.9, 7200.0, True, "PLAYING")


def test_a_steady_play_is_true_as_of_the_previous_request() -> None:
    """Стенд 06-10-2026: доклад 111.9 при ТВ на 114.6 - статус ответил на просьбу 2 с назад."""
    assert tv_since(PLAYING, PLAYING, asked=10.0) == 10.0


def test_a_report_right_after_a_buffer_gets_no_moment() -> None:
    """Статус, пришедший сам на переходе, мог быть свежим: досчёт увёл бы карточку вперёд."""
    assert tv_since(Position(82.8, 7200.0, True, "BUFFERING"), PLAYING, asked=10.0) is None


def test_the_first_report_gets_no_moment() -> None:
    assert tv_since(None, PLAYING, asked=10.0) is None
