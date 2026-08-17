"""Нога хоста: три поля, из которых считается подсеть к обходу."""

from __future__ import annotations

import ipaddress

from torrcast.adapters.chromecast.scan.net import Net


def test_the_leg_carries_exactly_what_a_subnet_is_counted_from() -> None:
    """Адрес и маска - это и есть подсеть; имя нужно только человеку в разборе."""
    net = Net("eth0", "10.0.0.7", "255.255.255.0")

    network = ipaddress.ip_network(f"{net.address}/{net.mask}", strict=False)

    assert str(network) == "10.0.0.0/24"
    assert net.name == "eth0"


def test_the_leg_is_a_value_and_not_a_mutable_record() -> None:
    """Ноги складывают в множества, чтобы одна подсеть не обходилась дважды."""
    assert (
        len({Net("eth0", "10.0.0.7", "255.255.255.0")} | {Net("eth0", "10.0.0.7", "255.255.255.0")})
        == 1
    )
