"""Проверяет контракт приёмника и поведение его фейка."""

from tests.fakes.receiver import FakeReceiver
from torrcast.domain.position import Position
from torrcast.ports.receiver import Receiver


def test_fake_records_receiver_control() -> None:
    fake = FakeReceiver(Position(5, 10, True))
    port: Receiver = fake
    port.play("url", "title", 3)
    assert port.position(8).pos == 5
    port.stop(True)
    assert (fake.plays, fake.fronts, fake.stops) == ([("url", "title", 3)], [8], [True])
