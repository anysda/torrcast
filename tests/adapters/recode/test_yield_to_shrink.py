"""Пауза захода ради ужатия на месте: живость ужатия подтверждается фактом, а не таймером."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from tests.adapters.recode.grids import grid, keys
from torrcast.adapters.recode.recoder_state import _State
from torrcast.adapters.recode.weights import Weights
from torrcast.adapters.recode.yield_to_shrink import (
    SHRINK_FRESH,
    _shrink_running,
    _shrink_touched,
    _yield_to_shrink,
)
from torrcast.domain.hls_settings import SHRINK_DIR

if TYPE_CHECKING:
    from pathlib import Path


class _Proc:
    """Процесс захода, который запоминает полученные сигналы."""

    def __init__(self) -> None:
        self.signals: list[int] = []

    def send_signal(self, number: int) -> None:
        self.signals.append(number)


class _Packer:
    def __init__(self) -> None:
        self.proc = _Proc()


def _state(spare: Path) -> _State:
    lines = grid()
    weights = Weights.of(keys(rate=2.0e6), lines)
    assert weights is not None
    return _State(source="src", audio=0, grid=lines, spare=spare, weights=weights, threshold=15.0)


def test_the_shrink_directory_is_the_witness_not_a_timer(tmp_path: Path) -> None:
    """Ужатие пишет свой сегмент непрерывно, и метка времени файла и есть признак жизни."""
    state = _state(tmp_path)

    assert _shrink_touched(state) == 0.0, "каталога нет - никто ничего не писал"
    room = tmp_path / SHRINK_DIR
    room.mkdir()
    (room / "v3.ts").write_bytes(b"x")

    assert _shrink_touched(state) > 0.0


def test_the_grace_covers_the_ffmpeg_of_the_shrinker_getting_up(tmp_path: Path) -> None:
    """Пока ffmpeg ужатия поднимается, каталог пуст не потому, что всё кончилось."""
    state = _state(tmp_path)
    state.shrinking = (3, time.monotonic())

    assert _shrink_running(state), "фора на подъём держится по заявке"


def test_a_stale_directory_means_the_shrinker_is_gone(tmp_path: Path) -> None:
    """Метка времени старше отпущенного - второго кодировщика на машине больше нет."""
    state = _state(tmp_path)
    room = tmp_path / SHRINK_DIR
    room.mkdir()
    stale = time.time() - SHRINK_FRESH - 1.0
    (room / "v3.ts").write_bytes(b"x")
    import os

    os.utime(room / "v3.ts", (stale, stale))
    state.shrinking = (3, time.monotonic() - state.startup - 0.1)

    assert not _shrink_running(state)
    assert state.shrinking is None, "заявка снимается вместе с ожиданием"


def test_nobody_shrinking_means_the_run_does_not_stall_at_all(tmp_path: Path) -> None:
    """Заход замирает по нужде, а не из вежливости: без ужатия он идёт как шёл."""
    state = _state(tmp_path)
    packer: Any = _Packer()

    assert _yield_to_shrink(state, packer) == 0.0
    assert packer.proc.signals == [], "лишних сигналов процессу не шлём"


def test_the_run_is_paused_and_woken_around_the_shrink(tmp_path: Path) -> None:
    """Процессор у ffmpeg отбирает только пауза: снятый заход выбросил бы уже посчитанное.

    Замер: рядом с ужатием заход идёт вдвое-втрое медленнее, то есть ползут оба.
    """
    import signal

    state = _state(tmp_path)
    packer: Any = _Packer()
    state.shrinking = (3, time.monotonic())
    state.stopped = True  # ждать в тесте нечего: проверяем пару сигналов вокруг паузы

    stalled = _yield_to_shrink(state, packer)

    assert stalled >= 0.0
    assert packer.proc.signals == [signal.SIGSTOP, signal.SIGCONT]


def test_a_ready_recode_ends_the_wait_even_while_the_directory_is_warm(tmp_path: Path) -> None:
    """Перекод доехал сам, пока ждали замок, - ужимать этот кусок больше некому."""
    state = _state(tmp_path)
    room = tmp_path / SHRINK_DIR
    room.mkdir()
    (room / "v3.ts").write_bytes(b"x")
    (tmp_path / "v3.ts").write_bytes(b"x")
    state.shrinking = (3, time.monotonic() - state.startup - 0.1)

    assert not _shrink_running(state)
