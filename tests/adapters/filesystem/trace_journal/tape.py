"""Ловушка записей для зеркал схемы событий: перехват укладки у фонового писателя.

Схема события - это его имя, его фаза и его поля с их округлением. Ловить её надо там,
где запись уходит в очередь, а не на файле ленты: файл пишет фоновый поток, и его
расписание к схеме отношения не имеет.
"""

from __future__ import annotations

from typing import Any

import pytest

from torrcast.adapters.filesystem.trace_journal.writer import _Writer

#: Общий конверт любой записи; зеркала схемы спрашивают про поля СВОЕГО события.
_ENVELOPE = frozenset({"at", "sid", "pid", "phase", "event"})

#: Один пойманный вызов: фаза, событие и поля ровно в том виде, в каком их поставили.
Call = tuple[str, str, dict[str, Any]]


def caught(monkeypatch: pytest.MonkeyPatch) -> list[Call]:
    """Перехватить укладку записей в очередь и складывать их разобранными на части."""
    seen: list[Call] = []

    def spy(_self: _Writer, record: dict[str, Any]) -> None:
        rest = {key: value for key, value in record.items() if key not in _ENVELOPE}
        seen.append((str(record["phase"]), str(record["event"]), rest))

    monkeypatch.setattr(_Writer, "put", spy)
    monkeypatch.setenv("TORRCAST_SID", "запуск")
    return seen
