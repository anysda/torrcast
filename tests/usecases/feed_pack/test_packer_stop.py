"""Конец прогона: чем он объясняется наружу и что после него остаётся на диске."""

from __future__ import annotations

import subprocess
from io import BytesIO
from typing import TYPE_CHECKING

from tests.usecases.feed_pack.world import FakeProc, lay, packer, signals
from torrcast.usecases.feed_pack.packer_stop import _stop, _why

if TYPE_CHECKING:
    from pathlib import Path


def _log(text: str) -> BytesIO:
    return BytesIO(text.encode("utf-8"))


def test_our_own_terminate_is_never_passed_off_as_a_crash(tmp_path: Path) -> None:
    """Прогон, снятый нами, объясняется нами же: ffmpeg по SIGTERM выходит кодом 255.

    Без этой строки собственный ``terminate`` неотличим от аварии, и показ ругался
    на труп, который сам же и снял.
    """
    run = packer(tmp_path, stopped="показ окончен", proc=FakeProc(code=255))

    assert _why(run) == "сняли сами: показ окончен"


def test_a_signal_kill_is_named_by_its_number_and_nothing_is_invented(tmp_path: Path) -> None:
    """Убитый сигналом сказать не успел - за него не выдумываем."""
    run = packer(tmp_path, proc=FakeProc(code=-9), log=_log("последняя строка"))

    assert _why(run) == "убит сигналом 9"


def test_the_last_word_of_ffmpeg_goes_out_trimmed_and_without_empty_lines(
    tmp_path: Path,
) -> None:
    """Наружу идёт последняя непустая строка ffmpeg, обрезанная до 120 знаков."""
    run = packer(tmp_path, proc=FakeProc(code=1), log=_log("first\nlast word\n\n"))

    assert _why(run) == "last word"

    long = packer(tmp_path, proc=FakeProc(code=1), log=_log("y" * 300))
    assert _why(long) == "y" * 120


def test_a_silent_run_is_answered_by_its_code_or_by_its_life(tmp_path: Path) -> None:
    """ffmpeg смолчал - отвечает код; кода нет вовсе - прогон ещё жив."""
    assert _why(packer(tmp_path, proc=FakeProc(code=0), log=_log(""))) == "молча, код 0"
    assert _why(packer(tmp_path)) == "нет вывода"


def test_stopping_a_live_run_terminates_it_and_hands_the_published_over(
    tmp_path: Path,
) -> None:
    """Снятие гасит процесс, зовёт выкладку и убирает свой каталог - но не показ."""
    laid: list[int] = []
    run = packer(tmp_path)
    lay(run.run, 0)
    lay(run.out, 1)

    _stop(run, lambda: laid.append(1), keep_files=True, reason="показ окончен")

    assert signals(run) == ["terminate"]
    assert laid == [1], "дописанное этим прогоном показу не отдали"
    assert not run.run.exists() and (run.out / "v1.ts").exists()
    assert run.stopped == "показ окончен"


def test_a_run_that_ignores_terminate_is_killed(tmp_path: Path) -> None:
    """Процесс, не ушедший по SIGTERM, добивается: висящий ffmpeg держит tmpfs и вход."""

    class _Stubborn(FakeProc):
        def terminate(self) -> None:
            self.signals.append("terminate")

        def wait(self, timeout: float | None = None) -> int:
            raise subprocess.TimeoutExpired("ffmpeg", timeout or 0.0)

    run = packer(tmp_path, proc=_Stubborn())

    _stop(run, lambda: None, keep_files=True)

    assert signals(run) == ["terminate", "kill"]


def test_without_keep_files_the_show_window_is_swept_clean(tmp_path: Path) -> None:
    """Снятие без сохранения выметает окно показа: следующая серия начинает с чистого."""
    run = packer(tmp_path)
    lay(run.out, 1)
    lay(run.out, 2)

    _stop(run, lambda: None)

    assert list(run.out.glob("v*.ts")) == []


def test_the_first_reason_of_a_stop_is_the_one_that_stays(tmp_path: Path) -> None:
    """Причина снятия пишется один раз: второй заход не переписывает первую."""
    run = packer(tmp_path, stopped="пауза на пульте")

    _stop(run, lambda: None, keep_files=True, reason="показ окончен")

    assert run.stopped == "пауза на пульте"
