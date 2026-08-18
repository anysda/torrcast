"""Зеркало мерки памяти: число берётся у среды, а не у машины, где идёт тест."""

from __future__ import annotations

import pytest

from tests.fakes.health_environment import FakeHealthEnvironment
from torrcast.usecases import doctor_environment as _state
from torrcast.usecases.machine_memory import machine_memory


def test_the_memory_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Сколько сказала среда, столько и памяти: своих измерений у мерки нет."""
    monkeypatch.setattr(_state, "environment", FakeHealthEnvironment(memory=3 * 1024**3))

    assert machine_memory() == 3 * 1024**3


def test_a_new_environment_is_answered_by_the_new_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Среду сменили - мерка отвечает уже по ней: значение не кэшируется на импорте."""
    monkeypatch.setattr(_state, "environment", FakeHealthEnvironment(memory=1))
    first = machine_memory()
    monkeypatch.setattr(_state, "environment", FakeHealthEnvironment(memory=2))

    assert (first, machine_memory()) == (1, 2)
