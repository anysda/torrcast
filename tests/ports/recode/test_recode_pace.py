"""Зеркало лестницы пресетов: настоящий замер темпа отвечает договору."""

from __future__ import annotations

from torrcast.ports.recode.recode_pace import RecodePace
from torrcast.recode import Pace


def test_the_real_pace_answers_the_named_contract() -> None:
    """Сценарии читают у темпа одну таблицу, и настоящий замер её отдаёт."""
    named: RecodePace = Pace()

    table = named.table()

    assert table, "лестница пресетов пуста - выбирать перекоду не из чего"
    preset, speed = table[0]
    assert isinstance(preset, str) and speed > 0
