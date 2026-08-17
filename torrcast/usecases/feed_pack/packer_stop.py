"""Конец прогона упаковки: почему он кончился и как его снять, ничего не потеряв.

Зовёт их сам прогон (:mod:`torrcast.usecases.feed_pack.packer`), а через него - показ.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import torrcast.usecases.feed_pack._state as _state
from torrcast.usecases.feed_pack._segment_files import _paths

if TYPE_CHECKING:
    from collections.abc import Callable

    from torrcast.usecases.feed_pack.packer_state import _State


def _why(state: _State) -> str:
    """Почему прогон кончился — наружу без трейсбеков.

    Порядок ответов честный: сначала «мы сами» (:attr:`stopped`), потом слово ffmpeg,
    и только если он промолчал — код возврата. Молчание при коде 255 не загадка, а
    подпись нашего же SIGTERM (см. :attr:`stopped`), и выдавать её за аварию нельзя.
    """
    if state.stopped:
        return f"сняли сами: {state.stopped}"
    code = state.proc.poll()
    if code is not None and code < 0:
        return f"убит сигналом {-code}"  # сказать он не успел - не выдумываем за него
    lines: list[str] = []
    if state.log is not None:
        state.log.seek(0)
        text = state.log.read().decode("utf-8", "replace")
        lines = [ln for ln in text.splitlines() if ln.strip()]
    if lines:
        return lines[-1][:120]
    return "нет вывода" if code is None else f"молча, код {code}"


def _stop(
    state: _State, publish: Callable[[], None], keep_files: bool = False, reason: str = ""
) -> None:
    """Снять прогон, оставив показу всё, что тот успел честно выложить.

    Выкладка приходит доводом, а не спрашивается у класса: снятие живёт внутри него.
    """
    state.stopped = state.stopped or reason
    if state.proc.poll() is None:
        state.proc.terminate()
        with contextlib.suppress(_state.subprocess.TimeoutExpired):
            state.proc.wait(timeout=5)
        if state.proc.poll() is None:
            state.proc.kill()
    publish()  # дописанное этим прогоном остаётся показу: оно уже верное
    _state.shutil.rmtree(state.run, ignore_errors=True)
    if not keep_files:
        for junk in _paths(state.out):
            junk.unlink(missing_ok=True)
