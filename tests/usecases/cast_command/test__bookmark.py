"""Зеркало закладки: продолжить, начать сначала, списать досмотренное - и сказать об этом."""

from __future__ import annotations

from typing import Any, cast

import pytest

from tests.usecases.cast_command.world import entry, plan
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.cast_command._bookmark import (
    _account_watched,
    _continue_picked,
    _plays_recorded,
)
from torrcast.usecases.start_clock import _Clock


class Bench:
    """Стенд отбора под наблюдением зеркала: важно, убрал ли он прогретое."""

    def __init__(self) -> None:
        self.dropped = 0

    def drop_all(self) -> None:
        self.dropped += 1


def _state_with(saved: object | None) -> WatchState:
    state = WatchState()
    if saved is not None:
        state.put(plan().picture.key, saved)  # type: ignore[arg-type]
    return state


def test_a_picture_without_a_bookmark_goes_the_usual_way() -> None:
    """Записи нет - продолжать нечего, и путь остаётся обычным."""
    code = _continue_picked(
        Config(),
        _state_with(None),
        cast(Any, plan()),
        Bench(),  # type: ignore[arg-type]
        args=Args(query=["кино"]),
        clock=_Clock(),
    )

    assert code is None


def test_a_hand_named_release_says_out_loud_that_it_drops_the_bookmark(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--release N`` значит «другая раздача», а не «забудь, где я остановился»."""
    bench = Bench()

    code = _continue_picked(
        Config(),
        _state_with(entry()),
        cast(Any, plan()),
        bench,  # type: ignore[arg-type]
        args=Args(query=["кино"], release=2),
        clock=_Clock(),
    )

    assert code is None, "названный руками релиз играется обычным путём"
    assert "сохранённое место 1:00:00 не поднимаю" in capsys.readouterr().out
    assert bench.dropped == 0, "прогретое тут ещё пригодится: показ пойдёт обычным путём"


def test_a_series_is_left_to_the_usual_way() -> None:
    """Сериал сюда не заходит: его продолжение ведёт своя ветка."""
    code = _continue_picked(
        Config(),
        _state_with(entry(kind="tv", season=1, episode=2, episodes=[(1, 1), (1, 2)])),
        cast(Any, plan()),
        Bench(),  # type: ignore[arg-type]
        args=Args(query=["кино"]),
        clock=_Clock(),
    )

    assert code is None


def test_a_watched_bookmark_becomes_watched_on_the_next_cast(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Закладка за порогом досмотра на следующем ``cast`` превращается в «досмотрено»."""
    state = WatchState()
    saved = entry(pos=7000.0)
    state.put("кино", saved)

    (key, following), moved = _account_watched(state, ("кино", saved))

    assert moved is True and key == "кино"
    assert following.pos == 0.0, "с начала - это ноль, а не прежнее место"
    assert "досмотрено на" in capsys.readouterr().out


def test_an_unfinished_bookmark_is_left_alone() -> None:
    """Место, до порога не доехавшее, - это место, а не досмотр."""
    state = WatchState()
    saved = entry(pos=100.0)
    state.put("кино", saved)

    found, moved = _account_watched(state, ("кино", saved))

    assert moved is False and found[1] is saved


def test_a_picture_without_a_bookmark_keeps_its_warm_under_the_menu() -> None:
    """Записи нет - прогреву этой картины сноситься нечем."""
    assert _plays_recorded(_state_with(None), plan().picture.key, Args(query=["кино"])) is False


def test_a_resumable_bookmark_answers_with_the_recorded_release() -> None:
    """Начатый и недосмотренный фильм продолжится записанной раздачей: прогрев снесётся."""
    assert _plays_recorded(_state_with(entry()), plan().picture.key, Args(query=["кино"])) is True


def test_a_series_bookmark_does_not_answer_for_the_warm() -> None:
    """Сериал продолжает своя ветка, а не закладка выбранной картины: прогрев живёт."""
    saved = entry(kind="tv", season=1, episode=2, episodes=[(1, 1), (1, 2)])

    assert _plays_recorded(_state_with(saved), plan().picture.key, Args(query=["кино"])) is False


def test_a_finished_bookmark_does_not_answer_for_the_warm() -> None:
    """Продолжать нечего - и сносить прогретое закладка не будет."""
    assert (
        _plays_recorded(_state_with(entry(done=True)), plan().picture.key, Args(query=["кино"]))
        is False
    )


def test_a_hand_named_release_keeps_the_warm() -> None:
    """``--release N`` играет выбранное руками: прогретое ещё пригодится."""
    assert (
        _plays_recorded(_state_with(entry()), plan().picture.key, Args(query=["кино"], release=2))
        is False
    )


def test_from_start_answers_with_the_recorded_release_from_zero() -> None:
    """``--new`` играет записанную раздачу с нуля - и тоже сносит прогретое."""
    assert (
        _plays_recorded(
            _state_with(entry()), plan().picture.key, Args(query=["кино"], from_start=True)
        )
        is True
    )


def test_from_start_with_a_hand_named_release_keeps_the_warm() -> None:
    """``--new`` вместе с названным руками релизом играет выбранное: прогрев живёт."""
    assert (
        _plays_recorded(
            _state_with(entry()),
            plan().picture.key,
            Args(query=["кино"], release=2, from_start=True),
        )
        is False
    )
