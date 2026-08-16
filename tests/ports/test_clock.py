"""Проверяет контракт часов и поведение их фейка."""

from tests.fakes.clock import FakeClock
from torrcast.ports.clock import Clock


def test_fake_advances_only_when_asked_to_sleep() -> None:
    fake = FakeClock(10)
    port: Clock = fake
    port.sleep(2.5)
    assert port.monotonic() == 12.5
    assert fake.sleeps == [2.5]
