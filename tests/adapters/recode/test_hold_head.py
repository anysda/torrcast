"""Голова прогона: ждать её, пока кодировщик над ней работает, а не пока не истёк срок."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from tests.adapters.recode.grids import grid, keys
from torrcast.adapters.recode.hold_head import HEAD_LIMIT, _head_pending, _hold_head
from torrcast.adapters.recode.recoder_state import _State
from torrcast.adapters.recode.weights import Weights

if TYPE_CHECKING:
    from pathlib import Path


def _state(spare: Path) -> _State:
    lines = grid()
    weights = Weights.of(keys(rate=2.0e6), lines)
    assert weights is not None
    return _State(source="src", audio=0, grid=lines, spare=spare, weights=weights, threshold=15.0)


def test_the_head_is_waited_for_while_the_wait_lasts(tmp_path: Path) -> None:
    """Голову ждёт чёрный экран: ждать тут значит не подгружаться, а стартовать."""
    state = _state(tmp_path)
    now = time.monotonic()
    state.head, state.head_at = 0, now

    assert _hold_head(state, now)
    assert not _hold_head(state, now + state.head_wait + 0.1), "отпущенное кончилось"


def test_a_recoder_working_on_the_head_gets_twice_the_patience(tmp_path: Path) -> None:
    """Замер на «Тачках 3»: голова кодировалась 16 с при потолке 12, и лишние 4 с бесплатны."""
    state = _state(tmp_path)
    now = time.monotonic()
    state.head, state.head_at = 0, now
    state.job = (0, 0, 0.0, now, 1.0)  # заход идёт ровно за головой

    late = now + state.head_wait + 1.0

    assert _hold_head(state, late), "над головой работают - ждём дольше"
    assert not _hold_head(state, now + state.head_wait * HEAD_LIMIT + 0.1), "но не бесконечно"
    assert HEAD_LIMIT == 2.0


def test_a_light_head_is_never_waited_for(tmp_path: Path) -> None:
    """Кусок, за который кодировщик не берётся, держать показ права не имеет."""
    lines = grid()
    light = Weights.of(keys(rate=0.5e6), lines)
    assert light is not None
    state = _State(source="src", audio=0, grid=lines, spare=tmp_path, weights=light, threshold=15.0)
    now = time.monotonic()
    state.head, state.head_at = 0, now

    assert not _hold_head(state, now)


def test_the_wait_switched_off_holds_nothing(tmp_path: Path) -> None:
    """Нулевое ожидание - это выключенная придержка головы, а не мгновенный срок."""
    state = _state(tmp_path)
    state.head, state.head_at, state.head_wait = 0, time.monotonic(), 0.0

    assert not _hold_head(state, time.monotonic())


def test_a_head_already_done_or_ready_is_not_pending(tmp_path: Path) -> None:
    """Готовый перекод головы ждать нечего - его возьмёт выкладка."""
    state = _state(tmp_path)
    state.head, state.head_at = 0, time.monotonic()

    assert _head_pending(state)
    (tmp_path / "v0.ts").write_bytes(b"x")
    assert not _head_pending(state), "перекод лежит - ожидание кончилось"
    (tmp_path / "v0.ts").unlink()
    state.done.add(0)
    assert not _head_pending(state), "кодировщик на голове сдался - ждать нечего"


def test_without_a_run_at_all_there_is_no_head_to_wait_for(tmp_path: Path) -> None:
    """Упаковка ещё не начиналась - головы нет, и придержка молчит."""
    state = _state(tmp_path)

    assert state.head == -1
    assert not _head_pending(state)
