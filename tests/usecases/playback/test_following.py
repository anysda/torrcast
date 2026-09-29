"""Зеркало договора о цепочке серий: ручка отдаёт прогрев следующей или молчит."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import pytest

from tests.usecases.warm.world import warmer
from torrcast.usecases.playback.following import Following, _holding, _PreparedFollowing
from torrcast.usecases.warm.settings import GUARD_HIGH, GUARD_LOW
from torrcast.usecases.warm.warmer import Warmer

if TYPE_CHECKING:
    from pathlib import Path


def test_a_movie_has_nothing_to_follow() -> None:
    """У фильма следующей серии нет и быть не может - ручка честно молчит."""

    def nothing() -> Warmer | None:
        return None

    named: Following = _PreparedFollowing(nothing)

    assert named() is None


def test_a_prepared_following_builds_once_before_the_chain_asks() -> None:
    """Первый кадр готовит паспорт соседа, цепочка получает тот же готовый ответ."""
    asked: list[int] = []

    def once() -> Warmer | None:
        asked.append(1)
        return None

    following = _PreparedFollowing(once)

    following.start()
    following.start()
    assert following() is None
    assert following() is None
    assert asked == [1], "цепочку спрашивают ровно один раз за серию"


def test_a_network_blink_on_the_first_frame_does_not_lock_the_next_episode_out() -> None:
    """Сбой сборки отдаётся цепочке, а следующий её вопрос собирает заново.

    Раньше ошибка запоминалась: сеть моргнула на первом кадре - и все повторы цепочки
    получали ту же ошибку, следующая серия не прогревалась никогда.
    """
    asked: list[int] = []
    ready = object()

    def blinking() -> Warmer | None:
        asked.append(1)
        if len(asked) == 1:
            raise OSError("network down")
        return ready  # type: ignore[return-value]

    following = _PreparedFollowing(blinking)
    following.start()

    with pytest.raises(OSError, match="network down"):
        following()
    assert following() is ready, "после сбоя сборка не повторилась"
    assert following() is ready
    assert asked == [1, 1]


def test_the_preparation_waits_while_the_live_window_needs_the_machine() -> None:
    """Пока живому показу нужен запас, сборка не задаёт раздаче ни одного вопроса."""
    asked = threading.Event()
    held = threading.Event()
    free = threading.Event()

    def build() -> Warmer | None:
        asked.set()
        return None

    def hold() -> bool:
        held.set()
        return not free.is_set()

    following = _PreparedFollowing(build, pause=0.001)
    following.start(hold)

    assert held.wait(5.0)
    assert not asked.wait(0.05), "сборка полезла в раздачу посреди живого окна"
    free.set()
    assert following() is None
    assert asked.is_set()


def test_the_preparation_is_held_by_the_same_rule_as_the_warming(tmp_path: Path) -> None:
    """Живому окну нужен запас - прогрев замер, и сборка соседа ждёт вместе с ним."""
    warm = warmer(tmp_path, slack=GUARD_LOW - 1.0)
    hold = _holding(warm)

    assert hold(), "сборка не уступила просевшему окну показа"
    warm.slack = GUARD_HIGH + 1.0
    assert not hold()
    warm.slack = GUARD_LOW - 1.0
    warm.stopped = True
    assert not hold(), "снятый показ держал бы сборку вечно"
    assert not _holding(None)()
