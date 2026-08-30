"""Английские надписи кластера юнита показа."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера юнита показа."""
    return {
        "worker.receiver_profile": "receiver profile: {title} - {how}",
    }
