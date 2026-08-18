"""Проверяет, что расклад круга уходит в недельный след и в фазы секундомера."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from torrcast.adapters.filesystem.trace_journal import records, shutdown
from torrcast.adapters.prowlarr.circle_trace import circle_trace
from torrcast.ports.journal import Silent, install


class _Spy(Silent):
    """Молчащая лента, которая запоминает фазы секундомера.

    Секундомер кладёт фазу в ленту событием ``timeline``; недельный след круга идёт
    мимо порта, прямо в файл, и читается оттуда же.
    """

    def __init__(self) -> None:
        self.marks: list[tuple[str, dict[str, Any]]] = []

    def emit(self, phase: str, event: str, **fields: Any) -> None:
        if phase == "timeline":
            self.marks.append((event, fields))


def _record(journal: Path) -> dict[str, Any]:
    shutdown()
    (row,) = [item for item in records() if item.get("event") == "indexers"]
    return row


@pytest.mark.machine
def test_след_несёт_весь_круг_поимённо(journal: Path) -> None:
    """Событие круга несёт время КАЖДОГО ответившего: elapsedTime истории Prowlarr врёт
    про провалившиеся и повторные попытки, и хвост круга без своего секундомера из следа
    не разобрать (TC-230)."""
    circle_trace(
        got={"Knaben": 12},
        silent=("RuTor",),
        banned=(),
        ms={"Knaben": 140},
        fallback=False,
        late=("Nyaa.si",),
        budgets={"RuTor": 3.0},
    )
    row = _record(journal)
    assert row["got"] == {"Knaben": 12}
    assert row["ms"] == {"Knaben": 140}
    assert row["silent"] == ["RuTor"]
    assert row["late"] == ["Nyaa.si"]
    assert row["fallback"] is False


def test_молчуны_и_заблокированные_идут_разными_фазами(journal: Path) -> None:
    """Молчун не ответил нам, а заблокированного мы и не спрашивали - Prowlarr не дал.
    Смешать их значит спрятать причину, по которой каталог урезан, за словом «молчит»."""
    spy = _Spy()
    install(spy)
    circle_trace(
        got={},
        silent=("RuTor",),
        banned=("YTS",),
        ms={},
        fallback=True,
        late=(),
        budgets={"RuTor": 3.0},
    )
    names = [name for name, _facts in spy.marks]
    assert names == ["индексеры", "индексеры"]
    assert spy.marks[0][1] == {"заблокированы": ["YTS"]}
    # Бюджет у каждого свой (TC-226), и в фазе он назван поимённо: иначе «молчит YTS,
    # бюджет 20 с» врало бы про то, сколько круг на нём простоял.
    assert spy.marks[1][1] == {"молчат": ["RuTor"], "бюджет": {"RuTor": 3.0}}


@pytest.mark.machine
def test_здоровый_круг_фаз_не_заводит(journal: Path) -> None:
    """Фаза - это про потерю; в следе такой круг всё равно записан целиком."""
    spy = _Spy()
    install(spy)
    circle_trace(
        got={"Knaben": 3}, silent=(), banned=(), ms={}, fallback=False, late=(), budgets={}
    )
    assert spy.marks == []
    assert _record(journal)["got"] == {"Knaben": 3}
