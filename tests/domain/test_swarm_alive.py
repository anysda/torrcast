"""Проверки признака живого роя."""

from torrcast.domain.swarm_alive import swarm_alive


def test_addresses_are_not_contacts() -> None:
    assert swarm_alive({"total_peers": 9, "half_open_peers": 9}) is False
