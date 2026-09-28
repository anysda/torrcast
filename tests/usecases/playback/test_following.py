"""Зеркало договора о цепочке серий: ручка отдаёт прогрев следующей или молчит."""

from __future__ import annotations

from torrcast.usecases.playback.following import Following, _PreparedFollowing
from torrcast.usecases.warm.warmer import Warmer


def test_a_movie_has_nothing_to_follow() -> None:
    """У фильма следующей серии нет и быть не может - ручка честно молчит."""

    def nothing() -> Warmer | None:
        return None

    named: Following = nothing

    assert named() is None


def test_the_handle_is_asked_and_answers_with_a_warmer() -> None:
    """Серия легла на диск - ручку зовут, и она отдаёт прогрев следующей."""
    asked: list[int] = []

    def once() -> Warmer | None:
        asked.append(1)
        return None

    named: Following = once
    named()

    assert asked == [1], "цепочку спрашивают ровно один раз за серию"


def test_a_prepared_following_builds_once_before_the_chain_asks() -> None:
    """Первый кадр готовит паспорт соседа, цепочка получает тот же готовый ответ."""
    asked: list[int] = []

    def once() -> Warmer | None:
        asked.append(1)
        return None

    following = _PreparedFollowing(once)

    following.start()
    assert following() is None
    assert asked == [1]
