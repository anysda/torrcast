"""Русские надписи кластера юнита показа."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера юнита показа."""
    return {
        "playback_session.stream_address_unknown": "адрес раздачи не определён",
    }
