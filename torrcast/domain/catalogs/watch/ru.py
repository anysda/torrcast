"""Русские надписи кластера сторожа позиции показа."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера сторожа позиции показа."""
    return {
        "watch.finished": "досмотрено{what}: {pos} из {duration}",
    }
