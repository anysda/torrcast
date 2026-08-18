"""Дверь в след: обязательный конверт записи и отказ от того, что не читается JSON'ом."""

from __future__ import annotations

from typing import Any

import pytest

from tests.fakes import composition
from tests.fakes.tape import FakeTape
from torrcast.adapters.filesystem.trace_journal.emit import emit


@pytest.fixture
def queued(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Записи ловятся там, где они уходят в очередь: диска этот путь не касается вовсе."""
    tape = FakeTape()
    composition.use_tape(monkeypatch, tape.put)
    monkeypatch.setenv("TORRCAST_SID", "запуск")
    return tape.records


def test_every_record_carries_the_envelope_that_makes_a_week_readable(
    queued: list[dict[str, Any]],
) -> None:
    """Конверт - время, сеанс, процесс, фаза и событие: по нему лента и разбирается.

    Убери из конверта сеанс - и записи одного ``cast`` станет нечем связать; убери
    процесс - и команда с юнитом показа сольются в одну ленту без автора.
    """
    emit("search", "query", query="матрица", raw=17)

    (record,) = queued
    assert record["phase"] == "search"
    assert record["event"] == "query"
    assert record["sid"] == "запуск"
    assert record["query"] == "матрица"
    assert record["raw"] == 17
    assert isinstance(record["at"], float)
    assert isinstance(record["pid"], int)


def test_the_fields_of_the_event_reach_the_record_whole(queued: list[dict[str, Any]]) -> None:
    """Поля кладутся поверх конверта целиком, а не отбираются по списку известных имён."""
    emit("play", "segment", slot=7, mb=3.5, extra=None)

    (record,) = queued
    assert record["slot"] == 7
    assert record["mb"] == 3.5
    assert record["extra"] is None


def test_a_record_that_is_not_json_is_dropped_instead_of_breaking_the_show(
    queued: list[dict[str, Any]],
) -> None:
    """Диагностика не имеет права ронять показ: несериализуемое поле роняет запись.

    Уйди такая запись в очередь - на ней бы и умер фоновый писатель, а вместе с ним
    замолчала бы вся лента.
    """
    emit("play", "segment", broken=object())

    assert queued == []
