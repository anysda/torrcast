"""Лента, которая никуда не пишет: записи остаются в списках стенда.

Схема события - это его имя, его фаза и его поля с их округлением, и ловится она там,
где запись уходит в очередь, а не на файле ленты: файл пишет фоновый поток, и его
расписание к схеме отношения не имеет.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Общий конверт любой записи; зеркала схемы спрашивают про поля СВОЕГО события.
ENVELOPE = frozenset({"at", "sid", "pid", "phase", "event"})

#: Один пойманный вызов: фаза, событие и поля ровно в том виде, в каком их поставили.
Call = tuple[str, str, dict[str, Any]]


@dataclass
class FakeTape:
    """Приёмник записей ленты: складывает всё, что ему положили, и ничего не пишет."""

    #: Записи целиком - вместе с конвертом: его проверяет зеркало самой двери в след.
    records: list[dict[str, Any]] = field(default_factory=list)
    #: Те же записи без конверта: так их спрашивают зеркала схемы событий.
    calls: list[Call] = field(default_factory=list)

    def put(self, record: dict[str, Any]) -> None:
        """Принять запись так же, как её принимает боевой писатель."""
        self.records.append(record)
        rest = {key: value for key, value in record.items() if key not in ENVELOPE}
        self.calls.append((str(record["phase"]), str(record["event"]), rest))
