"""Ноги хоста: спрос у ядра, только IPv4, и интерфейс без адреса просто пропускается."""

from __future__ import annotations

import socket

import pytest

from torrcast.adapters.chromecast.scan.interfaces import interfaces
from torrcast.adapters.chromecast.scan.net import Net


@pytest.mark.machine
def test_the_loopback_is_among_the_legs_the_kernel_names() -> None:
    """Опрос идёт у ядра, а не разбором вывода ``ip``: петля есть на любой машине.

    Разбор чужой утилиты означал бы зависимость установки от формата её вывода, а он
    меняется от дистрибутива к дистрибутиву.
    """
    nets = interfaces()

    assert all(isinstance(net, Net) for net in nets)
    assert any(net.address == "127.0.0.1" for net in nets), "петля обязана найтись"


@pytest.mark.machine
def test_every_leg_carries_an_ipv4_address_and_a_mask() -> None:
    """IPv6 не трогаем сознательно: приёмники живут на IPv4, а поход по IPv6 без внешнего
    маршрута кончается зависанием в SYN-SENT.
    """
    for net in interfaces():
        assert socket.inet_aton(net.address)
        assert socket.inet_aton(net.mask)


def test_an_interface_without_an_ipv4_address_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Интерфейс down, только с IPv6 или tun без адреса - это минус одна нога, не отказ.

    Ядро отвечает на такой ioctl ошибкой, и уронить на ней весь поиск значило бы не
    найти телевизор из-за поднятого рядом туннеля.
    """
    monkeypatch.setattr(socket, "if_nameindex", lambda: [(1, "мертвяк")])

    assert interfaces() == []
