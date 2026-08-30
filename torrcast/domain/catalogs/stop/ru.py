"""Русские надписи кластера остановки показа."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера остановки показа."""
    return {
        "stop.nothing_playing": "ничего не играет",
        "stop.stopped": "остановлено: «{title}» на {pos} / {duration}",
    }
