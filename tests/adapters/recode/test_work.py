"""Нитка кодировщика: заход за заходом, потолок кэша и запрет ронять показ."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.adapters.recode.grids import grid, keys
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


def test_the_thread_works_the_runs_it_picks(tmp_path: Path) -> None:
    """Нитка только выбирает заход и отрабатывает его - и так, пока идёт показ."""
    state = _state(tmp_path)
    done: list[tuple[int, int]] = []

    def _pick(seen: _State) -> tuple[int, int] | None:
        return (0, 2)

    def _run(seen: _State, first: int, last: int) -> None:
        done.append((first, last))
        seen.stopped = True

    _work(state, pick=_pick, run=_run)

    assert done == [(0, 2)]


def test_nothing_to_do_puts_the_thread_to_sleep_instead_of_spinning(tmp_path: Path) -> None:
    """Заходов нет - нитка спит, а не крутит процессор вхолостую."""
    state = _state(tmp_path)
    slept: list[float] = []

    def _sleep(seconds: float) -> None:
        slept.append(seconds)
        state.stopped = True

    _work(state, pick=lambda seen: None, nap=_sleep)

    assert slept == [1.0]


def test_the_cache_ceiling_stops_the_work_ahead_but_not_the_head(tmp_path: Path) -> None:
    """Уснуть под потолком кэша на голове значит отдать первый сегмент копией."""
    state = _state(tmp_path)
    state.cache_mb = 0.0  # потолок кэша достигнут всегда
    started: list[tuple[int, int]] = []
    slept: list[float] = []

    def _run(seen: _State, first: int, last: int) -> None:
        started.append((first, last))
        seen.stopped = True

    def _sleep(seconds: float) -> None:
        slept.append(seconds)
        state.stopped = True

    _work(state, pick=lambda seen: (0, 2), run=_run, nap=_sleep)
    assert started == [] and slept == [2.0], "запас впрок под потолком кэша ждёт"

    state.stopped, state.head = False, 0
    _work(state, pick=lambda seen: (0, 2), run=_run, nap=_sleep)
    assert started == [(0, 2)], "голову прогона потолок кэша не касается"


def test_a_failed_run_never_takes_the_show_down_with_it(tmp_path: Path) -> None:
    """Беда кодировщика - это в худшем случае тяжёлый кусок как есть, а не конец фильма."""
    said: list[str] = []
    state = _state(tmp_path)
    state.log = said.append

    def _boom(seen: _State) -> tuple[int, int] | None:
        raise RuntimeError("ffmpeg сгинул")

    def _sleep(seconds: float) -> None:
        state.stopped = True

    _work(state, pick=_boom, nap=_sleep)

    assert any("перекодирование сорвалось" in line for line in said)


def test_an_abandoned_run_is_retried_after_a_pause_not_in_a_spin(tmp_path: Path) -> None:
    """Брошенный заход повторяется после паузы, а не лавиной подъёмов ffmpeg.

    Условия броска (место показа, вставшая выкладка) меняются снаружи и не чаще, чем
    раз в две секунды, поэтому повтор раньше паузы - это заведомо тот же бросок плюс
    подъём процесса. Замер на вставшей выкладке: 416 подъёмов ffmpeg за 1.4 с.
    """
    state = _state(tmp_path)
    started: list[tuple[int, int]] = []
    slept: list[float] = []

    def _run(seen: _State, first: int, last: int) -> str:
        started.append((first, last))
        if len(started) == 2:
            seen.stopped = True
        return "упаковка встала на v0"

    _work(state, pick=lambda seen: (0, 2), run=_run, nap=slept.append)

    assert started == [(0, 2), (0, 2)]
    assert slept == [2.0], "между подъёмами одного и того же захода - пауза"


def test_a_new_job_after_an_abandon_runs_without_a_pause(tmp_path: Path) -> None:
    """Заход за другим куском после броска - не повтор, а новая работа: он не ждёт.

    Выкладка встала на v5 - заход за ней начинается немедленно, потому что его ждёт
    показ, а не запас впрок. Пауза стоит только на пути повтора ТОГО ЖЕ захода.
    """
    state = _state(tmp_path)
    jobs = iter([(0, 2), (5, 7)])
    started: list[tuple[int, int]] = []
    slept: list[float] = []

    def _pick(seen: _State) -> tuple[int, int] | None:
        return next(jobs)

    def _run(seen: _State, first: int, last: int) -> str:
        started.append((first, last))
        if len(started) == 2:
            seen.stopped = True
        return "упаковка встала на v5"

    _work(state, pick=_pick, run=_run, nap=slept.append)

    assert started == [(0, 2), (5, 7)]
    assert slept == [], "новый заход после броска ждать не должен: его ждёт показ"


def test_abandons_past_the_limit_give_the_job_up(tmp_path: Path) -> None:
    """Четвёртый бросок подряд - потолок: круг сдаётся, а не крутится на месте вечно.

    Куски числятся сделанными, как у захода, не давшего ни куска, - выкладка это
    видит и решает их сама. У упаковки тот же потолок в три обрыва подряд.
    """
    said: list[str] = []
    state = _state(tmp_path)
    state.log = said.append
    runs = 0

    def _run(seen: _State, first: int, last: int) -> str:
        nonlocal runs
        runs += 1
        if runs > 10:
            seen.stopped = True  # страховка от вечного круга, если потолок молчит
        return "упаковка встала на v0"

    def _sleep(seconds: float) -> None:
        if any("сдаюсь" in line for line in said):
            state.stopped = True

    _work(state, pick=lambda seen: (0, 2), run=_run, nap=_sleep)

    assert state.done == {0, 1, 2}, "за потолком повторов куски числятся сделанными"
    assert any("брошен" in line and "сдаюсь" in line for line in said)
