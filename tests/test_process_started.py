"""Проверяет миг старта процесса: он раньше старта фона на время подъёма службы."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

import web.process_started
from web.process_started import process_started

_AGED = (
    "import time; time.sleep(0.6); "
    "from web.process_started import process_started; "
    "print(time.monotonic() - process_started())"
)


@pytest.mark.machine
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="/proc is Linux")
def test_the_start_is_the_process_start_not_the_moment_of_the_question() -> None:
    """Процесс подождал 0.6 с до вопроса: старт на столько же раньше, а не «сейчас»."""
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        [sys.executable, "-c", _AGED], cwd=root, capture_output=True, text=True, check=True
    )
    age = float(out.stdout)
    assert 0.6 <= age < 30.0


def test_the_start_is_in_the_past_and_stays_put() -> None:
    """Старт не позже «сейчас» и не дрейфует между вопросами дальше тика часов."""
    first = process_started()
    assert first <= time.monotonic()
    assert abs(process_started() - first) < 0.05


def test_without_proc_the_start_is_the_moment_of_the_question(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Нет ``/proc`` (не Linux): старт - миг вопроса, прежний отсчёт от фона."""
    monkeypatch.setattr(web.process_started, "_STAT", tmp_path / "missing")
    before = time.monotonic()
    assert before <= process_started() <= time.monotonic()
