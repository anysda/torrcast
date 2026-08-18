"""Зеркало закладки: продолжить, начать сначала, списать досмотренное - и сказать об этом."""

from __future__ import annotations

from typing import Any, cast

import pytest

from tests.usecases.cast_command.world import entry, plan
from torrcast.cli.args import Args
from torrcast.domain.config import Config
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.cast_command._bookmark import _account_watched, _continue_picked
from torrcast.usecases.start_clock import _Clock


class _Bench:
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
        _Bench(),  # type: ignore[arg-type]
        args=Args(query=["кино"]),
        clock=_Clock(),
    )

    assert code is None


def test_a_hand_named_release_says_out_loud_that_it_drops_the_bookmark(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--release N`` значит «другая раздача», а не «забудь, где я остановился»."""
    bench = _Bench()

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
        _Bench(),  # type: ignore[arg-type]
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
