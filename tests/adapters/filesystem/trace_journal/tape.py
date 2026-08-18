"""Ловушка записей для зеркал схемы событий: подделка ленты на слоте фонового писателя.

Схема события - это его имя, его фаза и его поля с их округлением. Ловить её надо там,
где запись уходит в очередь, а не на файле ленты: файл пишет фоновый поток, и его
расписание к схеме отношения не имеет.
"""

from __future__ import annotations

import pytest

from tests.fakes import composition
from tests.fakes.tape import Call, FakeTape

__all__ = ["Call", "caught"]


def caught(monkeypatch: pytest.MonkeyPatch) -> list[Call]:
    """Поставить ленте подделку и отдать список, в который она складывает разобранное."""
    tape = FakeTape()
    composition.use_tape(monkeypatch, tape.put)
    monkeypatch.setenv("TORRCAST_SID", "запуск")
    return tape.calls
