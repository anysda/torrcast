"""Проверяет контракт поиска приёмников и поведение фейка."""

from tests.fakes.receiver_finder import FakeReceiverFinder
from torrcast.domain.receiver_info import ReceiverInfo
from torrcast.ports.receiver_finder import ReceiverFinder


def test_fake_records_filter_and_returns_receivers() -> None:
    found = ReceiverInfo("TV", "192.0.2.1")
    fake = FakeReceiverFinder([found])
    port: ReceiverFinder = fake
    assert port.find("TV") == [found]
    assert fake.names == ["TV"]
