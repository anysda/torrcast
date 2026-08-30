"""Русские надписи кластера поиска приёмников."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера поиска приёмников."""
    return {
        "chromecast_scan.searching": "ищу приёмники в сети",
        "chromecast_scan.unnamed_device": "приёмник",
        "chromecast_scan.subnets_skipped": (
            "слишком большие подсети не обхожу: {names} - если телевизор в одной из "
            "них, задай его адрес руками: cast --tv <ip>"
        ),
    }
