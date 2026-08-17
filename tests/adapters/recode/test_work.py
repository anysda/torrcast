"""Нитка кодировщика: заход за заходом, потолок кэша и запрет ронять показ."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest

from tests.adapters.recode.grids import grid, keys
from torrcast.adapters.recode import work as work_module
from torrcast.adapters.recode.recoder_state import _State
from torrcast.adapters.recode.weights import Weights
from torrcast.adapters.recode.work import _work

if TYPE_CHECKING:
    from pathlib import Path


def _state(spare: Path) -> _State:
    lines = grid()
    weights = Weights.of(keys(rate=2.0e6), lines)
    assert weights is not None
    return _State(source="src", audio=0, grid=lines, spare=spare, weights=weights, threshold=15.0)


def test_the_thread_works_the_runs_it_picks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Нитка только выбирает заход и отрабатывает его - и так, пока идёт показ."""
    state = _state(tmp_path)
    done: list[tuple[int, int]] = []

    def _pick(seen: _State) -> tuple[int, int] | None:
        return (0, 2)

    def _run(seen: _State, first: int, last: int) -> None:
        done.append((first, last))
        seen.stopped = True

    monkeypatch.setattr(work_module, "_pick", _pick)
    monkeypatch.setattr(work_module, "_run", _run)

    _work(state)

    assert done == [(0, 2)]


def test_nothing_to_do_puts_the_thread_to_sleep_instead_of_spinning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Заходов нет - нитка спит, а не крутит процессор вхолостую."""
    state = _state(tmp_path)
    slept: list[float] = []

    def _sleep(seconds: float) -> None:
        slept.append(seconds)
        state.stopped = True

    monkeypatch.setattr(work_module, "_pick", lambda seen: None)
    monkeypatch.setattr(time, "sleep", _sleep)

    _work(state)

    assert slept == [1.0]


def test_the_cache_ceiling_stops_the_work_ahead_but_not_the_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Уснуть под потолком кэша на голове значит отдать первый сегмент копией."""
    state = _state(tmp_path)
    state.cache_mb = 0.0  # потолок кэша достигнут всегда
    started: list[tuple[int, int]] = []
    slept: list[float] = []

    def _run(seen: _State, first: int, last: int) -> None:
        started.append((first, last))
        seen.stopped = True

    monkeypatch.setattr(work_module, "_pick", lambda seen: (0, 2))
    monkeypatch.setattr(work_module, "_run", _run)

    def _sleep(seconds: float) -> None:
        slept.append(seconds)
        state.stopped = True

    monkeypatch.setattr(time, "sleep", _sleep)
    _work(state)
    assert started == [] and slept == [2.0], "запас впрок под потолком кэша ждёт"

    state.stopped, state.head = False, 0
    _work(state)
    assert started == [(0, 2)], "голову прогона потолок кэша не касается"


def test_a_failed_run_never_takes_the_show_down_with_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Беда кодировщика - это в худшем случае тяжёлый кусок как есть, а не конец фильма."""
    said: list[str] = []
    state = _state(tmp_path)
    state.log = said.append

    def _boom(seen: _State) -> tuple[int, int] | None:
        raise RuntimeError("ffmpeg сгинул")

    def _sleep(seconds: float) -> None:
        state.stopped = True

    monkeypatch.setattr(work_module, "_pick", _boom)
    monkeypatch.setattr(time, "sleep", _sleep)

    _work(state)

    assert any("перекодирование сорвалось" in line for line in said)
