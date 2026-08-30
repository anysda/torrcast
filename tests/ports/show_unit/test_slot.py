"""Слот назначенного юнита показа: кто играет прямо сейчас и кто это назначает."""

import pytest

from tests.fakes.show_unit import FakeShowUnit
from torrcast.ports.show_unit.slot import Slot, install, unit


def test_a_fresh_slot_refuses_instead_of_saying_nothing_plays() -> None:
    """Пустой слот отказывает вслух, а не утверждает, что показа нет.

    «Ничего не играет» - утверждение о юните, а не его отсутствие, и врёт оно в обе
    стороны: уборка по нему сносит раздачу из-под живого показа, а запуск заводит
    второй показ поверх играющего, не погасив первый.
    """
    slot = Slot()

    with pytest.raises(RuntimeError, match="not assembled"):
        slot.current()


def test_the_installed_unit_is_what_the_scenarios_get() -> None:
    """Назначенный юнит и отдаётся: сценарии смотрят в тот же слот."""
    fake = FakeShowUnit(alive=True)
    install(fake)

    assert unit() is fake
    assert unit().active()
