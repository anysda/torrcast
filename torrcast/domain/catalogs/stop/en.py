"""Английские надписи кластера остановки показа."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера остановки показа."""
    return {
        "stop.nothing_playing": "nothing is playing",
        "stop.stopped": "stopped: “{title}” at {pos} / {duration}",
    }
