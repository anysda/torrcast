"""Проверяет оживление показа на фейковых часах и приёмнике."""

from tests.fakes.clock import FakeClock
from tests.fakes.receiver import FakeReceiver
from torrcast.domain.position import Position
from torrcast.usecases.revive import Revive


def test_revive_waits_and_restarts_from_saved_position() -> None:
    clock = FakeClock()
    receiver = FakeReceiver(Position(31.0, 100.0))

    Revive(receiver, clock).run("http://stream", "Фильм", 31.0, 4.0)

    assert clock.sleeps == [4.0]
    assert receiver.plays == [("http://stream", "Фильм", 31.0)]
