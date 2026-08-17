"""Придержка копии: ждать перекод стоит ровно тогда, когда он успеет раньше показа."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from tests.adapters.recode.grids import grid, keys
from torrcast.adapters.recode.holding import _holding
from torrcast.adapters.recode.recoder_state import _State
from torrcast.adapters.recode.weights import Weights

if TYPE_CHECKING:
    from pathlib import Path


def _state(spare: Path, rate: float = 1.5e6) -> _State:
    """Кодировщик на кино 12 Мбит/с: тяжелее порога, но копия ещё влезает в потолок веса.

    Ровно так и различаются два правила: срок решает только там, где вес копии не решает
    всё сам (:func:`_hold_bulky`).
    """
    lines = grid()
    weights = Weights.of(keys(rate=rate), lines)
    assert weights is not None
    state = _State(source="src", audio=0, grid=lines, spare=spare, weights=weights, threshold=10.0)
    assert not state.oversize(1), "копия под потолком веса: судить будет срок"
    assert 1 in state.targets, "и при этом кусок для кодировщика тяжёлый"
    return state


def test_a_ready_recode_needs_no_holding_at_all(tmp_path: Path) -> None:
    """Перекод уже лежит - выкладка возьмёт его сама, держать нечего."""
    state = _state(tmp_path)
    state.stuck[5], state.blocked = time.monotonic(), 5
    (tmp_path / "v5.ts").write_bytes(b"x")

    assert not _holding(state, 5)
    assert state.blocked == -1, "и слот перестаёт числиться держащим выкладку"


def test_a_piece_the_show_has_already_reached_is_never_held(tmp_path: Path) -> None:
    """Ожидание под носом у показа - это и есть подгруз."""
    state = _state(tmp_path)
    state.played = 100.0

    assert not _holding(state, 5), "показ уже прошёл этот кусок"


def test_between_runs_the_copy_still_waits_if_the_recoder_can_make_it(tmp_path: Path) -> None:
    """Заход не идёт - кодировщик поднимается или стоит МЕЖДУ заходами, а это секунды.

    Прежний отказ по истечении форы стоил живого прогона: «тяжёлый v359 ушёл копией:
    заход не идёт», а на экране - 16 опросов BUFFERING из 34.
    """
    state = _state(tmp_path)
    state.played, state.began = 0.0, time.monotonic()

    assert _holding(state, 20), "до куска 200 с - успеет и с подъёмом захода"
    assert not _holding(state, 1), "а до соседнего куска секунды: не успеет"


def test_a_piece_inside_the_running_run_waits_by_the_time_left_to_it(tmp_path: Path) -> None:
    """Внутри захода срок считается по тому, сколько кодировщику осталось до этого куска."""
    state = _state(tmp_path)
    now = time.monotonic()
    state.played = 0.0
    state.job = (0, 3, now + 100.0, now, 10.0)  # быстрый заход на куски 0...3

    assert _holding(state, 3), "заход дойдёт до куска раньше показа"

    state.job = (0, 3, now + 100.0, now, 0.05)  # тот же заход, но еле ползёт
    assert not _holding(state, 3), "к сроку не успевает - копия уходит как есть"


def test_a_run_whose_deadline_has_passed_holds_nothing(tmp_path: Path) -> None:
    """Просроченный заход держать копии не вправе: подгруз хуже тяжёлого куска."""
    state = _state(tmp_path)
    now = time.monotonic()
    state.played = 0.0
    state.job = (0, 3, now - 1.0, now - 50.0, 10.0)

    assert not _holding(state, 3)


def test_pieces_beyond_the_next_run_are_not_guessed_about(tmp_path: Path) -> None:
    """Дальше следующего захода планов у кодировщика нет: там решат перемотка и потолок кэша."""
    state = _state(tmp_path)
    now = time.monotonic()
    state.played = 0.0
    state.job = (0, 1, now + 1000.0, now, 10.0)

    assert _holding(state, 3), "кусок сразу за заходом ещё считается"
    assert not _holding(state, 1 + state.run_max + 1), "а дальше следующего захода - нет"
