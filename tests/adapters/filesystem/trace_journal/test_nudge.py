"""Схема ``play/nudge``: где стоял приёмник, куда прыгнули и было ли чем его кормить."""

from __future__ import annotations

import pytest

from tests.adapters.filesystem.trace_journal.tape import caught
from torrcast.adapters.filesystem.trace_journal.nudge import nudge


def test_the_jump_is_written_with_the_reason_to_tell_a_stall_from_honest_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """В записи стоят и застой, и упакованный фронт: без ``front`` их не различить.

    Приёмник в BUFFERING - это либо зависание, либо законное ожидание упаковки, и
    лечится это разным. Запись без фронта отвечала бы на вопрос «прыгал ли сторож», а
    нужен ответ «имел ли он право прыгать».
    """
    seen = caught(monkeypatch)

    nudge(pos=103.64, to=119.21, hit=2, stuck=8.44, front=180.06)

    assert seen == [
        (
            "play",
            "nudge",
            {"pos": 103.6, "to": 119.2, "hit": 2, "stuck": 8.4, "front": 180.1},
        )
    ]
