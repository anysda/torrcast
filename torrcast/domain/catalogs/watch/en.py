"""Английские надписи кластера сторожа позиции показа."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера сторожа позиции показа."""
    return {
        "watch.finished": "watched{what}: {pos} of {duration}",
    }
