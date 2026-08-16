"""Tests for the discovered-receiver value."""

from torrcast.domain.receiver_info import ReceiverInfo


def test_keeps_network_identity() -> None:
    assert ReceiverInfo("TV", "192.0.2.1").address == "192.0.2.1"
