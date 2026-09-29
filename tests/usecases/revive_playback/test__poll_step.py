"""Зеркало шага опроса приёмника: где круг учащается, а где идёт обычные две секунды."""

from __future__ import annotations

from torrcast.domain.position import Position
from torrcast.domain.start_settings import END_POLL_WINDOW, FIRST_FRAME_POLL
from torrcast.usecases.revive_playback._poll_step import POLL_SECONDS, _poll_step
from torrcast.usecases.revive_playback._screen_state import _Screen


def _shown() -> _Screen:
    """Экран, на котором кадр уже показан: окна старта нет."""
    return _Screen(seen=True)


def test_the_middle_of_an_episode_goes_the_usual_step() -> None:
    assert _poll_step(_shown(), Position(100.0, 1000.0, True, "PLAYING")) == POLL_SECONDS


def test_the_last_seconds_of_an_episode_are_polled_often() -> None:
    """Конец потока показ узнаёт на опросе - следующая серия не ждёт лишних двух секунд."""
    near = Position(1000.0 - END_POLL_WINDOW + 1.0, 1000.0, True, "PLAYING")
    assert _poll_step(_shown(), near, joins=True) == FIRST_FRAME_POLL


def test_the_end_without_a_next_episode_keeps_the_usual_step() -> None:
    """Фильм и последняя серия стыка не имеют - конец их учащать незачем."""
    near = Position(1000.0 - END_POLL_WINDOW + 1.0, 1000.0, True, "PLAYING")
    assert _poll_step(_shown(), near) == POLL_SECONDS


def test_a_pause_at_the_end_keeps_the_usual_step() -> None:
    """Пауза у титров может длиться час - учащать там нечего."""
    assert _poll_step(_shown(), Position(995.0, 1000.0, False, "PAUSED"), True) == POLL_SECONDS


def test_an_unknown_length_is_not_the_end() -> None:
    assert _poll_step(_shown(), Position(100.0, 0.0, True, "PLAYING"), True) == POLL_SECONDS


def test_the_start_window_is_polled_often_until_the_first_frame() -> None:
    waiting = _Screen(still_at=0.0)
    assert _poll_step(waiting, Position(0.0, 1000.0, True, "PLAYING")) == FIRST_FRAME_POLL
