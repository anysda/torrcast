"""Слишком увесистая копия: её не отпускают по сроку, потому что отпускать её некуда."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from tests.adapters.recode.grids import grid, keys
from torrcast.adapters.recode.hold_bulky import _hold_bulky
from torrcast.adapters.recode.recoder_state import _State
from torrcast.adapters.recode.weights import Weights

if TYPE_CHECKING:
    from pathlib import Path


def _state(spare: Path, said: list[str] | None = None) -> _State:
    lines = grid()
    weights = Weights.of(keys(rate=2.0e6), lines)
    assert weights is not None
    return _State(
        source="src",
        audio=0,
        grid=lines,
        spare=spare,
        weights=weights,
        threshold=15.0,
        log=None if said is None else said.append,
    )


def test_the_first_refusal_stops_the_publisher_and_says_so(tmp_path: Path) -> None:
    """Замер: 51.4 МБ на ТВ - двадцать опросов BUFFERING за 46 с. Такую копию не отпускают."""
    said: list[str] = []
    state = _state(tmp_path, said)
    now = time.monotonic()

    assert _hold_bulky(state, 3, now)
    assert state.blocked == 3, "выкладка встала на этом слоте, и заход об этом узнает"
    assert state.stuck[3] == now
    assert any("жду перекод" in line for line in said)


def test_the_wait_is_capped_so_a_dead_recoder_cannot_hold_the_show(tmp_path: Path) -> None:
    """Предохранитель - на случай, когда ffmpeg не поднимается вовсе."""
    state = _state(tmp_path)
    began = time.monotonic()

    assert _hold_bulky(state, 3, began)
    assert _hold_bulky(state, 3, began + state.over_wait - 0.1)
    assert not _hold_bulky(state, 3, began + state.over_wait + 0.1), "срок предохранителя вышел"
    assert state.blocked == -1 and 3 not in state.stuck
    assert state.shrinking is not None and state.shrinking[0] == 3


def test_a_slot_the_recoder_does_not_take_goes_straight_to_the_shrinker(tmp_path: Path) -> None:
    """Профиль тяжести промахнулся мимо этого куска - ждать нечего, ужмёт его выкладка."""
    lines = grid()
    light = Weights.of(keys(rate=0.5e6), lines)
    assert light is not None
    state = _State(source="src", audio=0, grid=lines, spare=tmp_path, weights=light, threshold=15.0)
    now = time.monotonic()

    assert not _hold_bulky(state, 2, now)
    assert state.shrinking == (2, now), "заявка на ужатие ставится ровно здесь"
    assert state.blocked == -1


def test_a_slot_the_recoder_gave_up_on_is_not_waited_for_either(tmp_path: Path) -> None:
    """Кодировщик уже сдался на этом куске - второй раз он за него не возьмётся."""
    state = _state(tmp_path)
    state.done.add(3)

    assert not _hold_bulky(state, 3, time.monotonic())
    assert state.shrinking is not None and state.shrinking[0] == 3


def test_a_stopped_recoder_holds_nothing(tmp_path: Path) -> None:
    """Показ кончился - держать выкладку некому и незачем."""
    state = _state(tmp_path)
    state.stopped = True

    assert not _hold_bulky(state, 3, time.monotonic())
    assert state.shrinking is None, "и заявку на ужатие снятый кодировщик не ставит"
