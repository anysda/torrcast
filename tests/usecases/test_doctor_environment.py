"""Зеркало общего места среды: слово композиции видят все её читатели разом."""

from __future__ import annotations

from tests.fakes.health_environment import FakeHealthEnvironment
from torrcast.usecases import doctor_environment as _state
from torrcast.usecases.disk_free import disk_free
from torrcast.usecases.doctor import _configure
from torrcast.usecases.machine_memory import machine_memory


def test_the_composition_word_reaches_every_reader() -> None:
    """Среду кладут один раз, а спрашивают её и пробы, и обе мерки машины."""
    previous = getattr(_state, "environment", None)
    given = FakeHealthEnvironment(memory=5, free=6, port=1234)
    try:
        _configure(given)

        assert _state.environment is given
        assert (machine_memory(), disk_free("/tmp")) == (5, 6)
    finally:
        if previous is not None:
            _configure(previous)


def test_the_slot_is_empty_until_the_composition_speaks() -> None:
    """До слова композиции имя объявлено, но значения у него нет: подделки не бывает."""
    assert "environment" in _state.__annotations__
