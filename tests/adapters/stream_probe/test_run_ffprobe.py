"""Запуск ffprobe: живой релиз проходит как раньше, молчащий рой обрывается рано."""

from __future__ import annotations

import subprocess
import sys

import pytest

from torrcast.adapters.stream_probe.run_ffprobe import _run_ffprobe
from torrcast.domain.swarm_error import SwarmError

_SAY = [sys.executable, "-c", "print('паспорт')"]
_FAIL = [sys.executable, "-c", "import sys; sys.stderr.write('плохо'); sys.exit(3)"]
_HANG = [sys.executable, "-c", "import time; time.sleep(30)"]


def test_without_a_pulse_the_call_is_the_plain_old_one() -> None:
    """Прежний путь обязан остаться прежним: та же команда и тот же срок."""
    assert _run_ffprobe(_SAY, timeout=10.0, alive=None).strip() == "паспорт"


def test_with_a_pulse_a_living_release_passes_exactly_as_before() -> None:
    """Признак жизни True всё время - ни одной лишней секунды не добавляется."""
    assert _run_ffprobe(_SAY, timeout=10.0, alive=lambda: True).strip() == "паспорт"


def test_a_silent_swarm_breaks_the_wait_long_before_the_budget() -> None:
    """Раздача с мёртвым роем метаданные отдаёт, а содержимого не отдаёт вовсе.

    Ffprobe на такой молча сидит весь срок, и досиживать его незачем: запасной релиз
    уже греется параллельно.
    """
    with pytest.raises(SwarmError, match="рой молчит"):
        _run_ffprobe(_HANG, timeout=30.0, alive=lambda: False)


def test_the_budget_is_still_the_last_word() -> None:
    """Рой жив, а заголовок не едет - срок обязан кончиться сам."""
    with pytest.raises(subprocess.TimeoutExpired):
        _run_ffprobe(_HANG, timeout=0.6, alive=lambda: True)


@pytest.mark.parametrize("alive", [None, lambda: True])
def test_a_failed_probe_is_raised_the_same_way_on_both_paths(alive: object) -> None:
    """Оба пути обязаны отличать «не прочитал поток» от «не дождался» одинаково."""
    with pytest.raises(subprocess.CalledProcessError):
        _run_ffprobe(_FAIL, timeout=10.0, alive=alive)
