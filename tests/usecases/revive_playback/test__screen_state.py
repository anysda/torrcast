"""Зеркало памяти экрана: чем показ начинает круг опроса и чего он про себя не выдумывает."""

from __future__ import annotations

import pytest

from torrcast.usecases.revive_playback._screen_state import _Screen

#: Имя поля, которого у объекта нет и быть не должно. Названо переменной, а не
#: точкой: через точку это выглядело бы объявлением НАШЕГО поля - и для читателя, и
#: для поиска мёртвого кода, который считает такое присваивание объявлением.
FOREIGN_FIELD = "invented"


def test_a_fresh_screen_has_neither_a_bookmark_nor_a_first_frame() -> None:
    """Закладка нулевая, указатель ``PLAYING`` не назван, хвост ещё не стоял."""
    screen = _Screen()

    assert (screen.held, screen.last, screen.paused, screen.said) == (0.0, 0.0, 0.0, 0.0)
    assert (screen.still_at, screen.tail_at, screen.tail_since) == (-1.0, -1.0, 0.0)
    assert (screen.seen, screen.buffering, screen.was_offline) == (False, False, False)


def test_the_start_is_taken_as_raised_unless_told_otherwise() -> None:
    """Показ считается поднятым, пока держатель не сказал обратного своим доводом."""
    assert _Screen().raised is True
    assert _Screen(raised=False).raised is False


def test_the_screen_holds_nothing_it_was_not_asked_to_hold() -> None:
    """Лишнего поля к памяти экрана не приписать: она объявлена целиком и закрыта."""
    with pytest.raises(AttributeError):
        setattr(_Screen(), FOREIGN_FIELD, 1)
