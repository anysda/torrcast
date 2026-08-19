"""Слот назначенного юнита показа: кто играет прямо сейчас и кто это назначает."""

from tests.fakes.show_unit import FakeShowUnit
from torrcast.ports.show_unit.idle import Idle
from torrcast.ports.show_unit.slot import Slot, install, unit


def test_a_fresh_slot_plays_nothing_until_the_root_says_otherwise() -> None:
    """До слова композиционного корня юнита нет вовсе."""
    slot = Slot()

    assert isinstance(slot.current(), Idle)


def test_the_installed_unit_is_what_the_scenarios_get() -> None:
    """Назначенный юнит и отдаётся: сценарии смотрят в тот же слот."""
    fake = FakeShowUnit(alive=True)
    install(fake)

    assert unit() is fake
    assert unit().active()
