"""Русские надписи кластера юнита показа."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера юнита показа."""
    return {
        "worker.receiver_profile": "профиль приёмника: {title} - {how}",
    }
