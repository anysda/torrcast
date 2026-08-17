"""Адреса подсетей к обходу, без наших собственных: сами себе мы не телевизор.

Разворачивает их поиск приёмников перед параллельным обходом."""

from __future__ import annotations

import ipaddress


def hosts(networks: list[str], ours: set[str]) -> list[str]:
    """Адреса подсетей к обходу, без наших собственных: сами себе мы не телевизор."""
    out: list[str] = []
    for key in networks:
        for address in ipaddress.ip_network(key).hosts():
            text = str(address)
            if text not in ours:
                out.append(text)
    return out
