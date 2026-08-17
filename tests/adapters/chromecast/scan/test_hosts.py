"""Адреса к обходу: вся подсеть без сети и брода, и без наших собственных адресов."""

from __future__ import annotations

from torrcast.adapters.chromecast.scan.hosts import hosts


def test_our_own_addresses_are_not_scanned() -> None:
    """Сами себе мы не телевизор: свой адрес из обхода вычёркивается."""
    addresses = hosts(["10.0.0.0/24"], {"10.0.0.7"})

    assert len(addresses) == 253
    assert "10.0.0.7" not in addresses
    assert addresses[0] == "10.0.0.1" and addresses[-1] == "10.0.0.254"


def test_several_subnets_come_back_as_one_list_to_walk() -> None:
    """Обход один на все ноги: бюджет времени тоже один, и делить его нечем."""
    addresses = hosts(["10.0.0.0/30", "10.0.1.0/30"], set())

    assert addresses == ["10.0.0.1", "10.0.0.2", "10.0.1.1", "10.0.1.2"]
