"""Штатный выход: хвост ленты дожимается, а не теряется вместе с процессом."""

from __future__ import annotations

from pathlib import Path

import pytest

from torrcast.adapters.filesystem.trace_journal.emit import emit
from torrcast.adapters.filesystem.trace_journal.shutdown import shutdown


def test_the_tail_of_the_tape_is_pressed_out_on_a_normal_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Записанное перед выходом обязано оказаться на диске: команда кончилась - след есть.

    Писатель - демон, и без этого вызова хвост ленты уходил бы вместе с процессом. Для
    аварийного конца это допустимо, для штатного - нет: именно последние записи и
    объясняют, чем кончился показ.
    """
    monkeypatch.setenv("TORRCAST_LOG", str(tmp_path))
    monkeypatch.setenv("TORRCAST_SID", "запуск")

    emit("session", "bye", why="конец")
    shutdown()

    written = sorted(tmp_path.glob("trace-*.jsonl"))
    assert len(written) == 1
    assert '"bye"' in written[0].read_text("utf-8")


def test_shutting_down_twice_is_not_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Второй выход зовут и корень запуска, и щупы: он обязан быть безобидным."""
    monkeypatch.setenv("TORRCAST_LOG", str(tmp_path))

    shutdown()
    shutdown()
