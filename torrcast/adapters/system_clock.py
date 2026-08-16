"""Часы поверх стандартного модуля времени: их получают сценарии, которым нужен срок.
Собирает их композиция команд (:mod:`torrcast.runtime`).
"""

from __future__ import annotations

import time


class SystemClock:
    """Реализация порта часов: монотонный отсчёт, стенные часы и настоящее ожидание."""

    def monotonic(self) -> float:
        return time.monotonic()

    def wall(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)
