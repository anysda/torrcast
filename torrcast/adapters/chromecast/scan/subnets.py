"""Подсети, годные к обходу, и отдельно те, что шире потолка.

Считает их поиск приёмников; о широких говорит одной строкой :func:`skipped`."""

from __future__ import annotations

import ipaddress
from typing import Final

from torrcast.adapters.chromecast.scan.net import Net

#: Потолок одной подсети. ``/24`` (254 адреса) проходит, ``/16`` (65534) - нет: обход
#: такой сети занял бы минуты, а телевизор в ней всё равно ищут не перебором.
MAX_HOSTS: Final = 1024


def subnets(nets: list[Net], limit: int = MAX_HOSTS) -> tuple[list[str], list[str]]:
    """Подсети, годные к обходу, и отдельно - те, что шире потолка.

    Отсекаем то, где искать нечего или дорого: петлю, link-local, ``/32`` (точка-точка,
    соседей нет по определению) и сети шире потолка. Потолок - не вкусовщина: ``/16``
    это 65534 адреса, то есть минуты обхода вместо секунд, и молча уйти в такой обход
    хуже, чем честно сказать «эту подсеть не смотрю, задай адрес руками».

    Про широкие возвращаем не текст, а сами подсети: сказать о них надо **одной** строкой
    (:func:`skipped`). На хосте с docker'ом таких сетей сразу три, и три одинаковых
    абзаца перед меню - это шум, за которым не видно самого списка.
    """
    seen: set[str] = set()
    good: list[str] = []
    huge: list[str] = []
    for net in nets:
        try:
            network = ipaddress.ip_network(f"{net.address}/{net.mask}", strict=False)
        except ValueError:
            continue
        if network.is_loopback or network.is_link_local or network.is_multicast:
            continue
        if network.prefixlen >= 31:  # точка-точка: обходить в ней некого
            continue
        key = str(network)
        if key in seen:
            continue
        seen.add(key)
        if network.num_addresses - 2 > limit:
            huge.append(key)
            continue
        good.append(key)
    return good, huge
