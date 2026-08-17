"""Проверяет контракт юнита показа и поведение его фейка."""

from tests.fakes.show_unit import FakeShowUnit
from torrcast.ports.show_unit import ShowUnit


def test_a_stopped_unit_is_not_alive_any_more() -> None:
    fake = FakeShowUnit()
    port: ShowUnit = fake

    assert port.active() and port.why() == "юнит ещё идёт к картинке"
    port.stop()

    assert not port.active(), "погашенный юнит живым себя больше не зовёт"
    assert fake.stops == [1]
