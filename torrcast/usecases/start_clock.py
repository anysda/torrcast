"""Часы фаз старта показа: сколько заняла каждая ступень до картинки на экране.
Заводят их команда показа и цикл юнита, читает их вслух прогресс.
"""

from __future__ import annotations

__all__ = ["_Clock"]

import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class _Clock:
    """Фазы старта: холодный старт стоит 15–30 с, и цифры должны быть видны глазами."""

    start: float = field(default_factory=time.monotonic)
    last: float = field(default_factory=time.monotonic)

    def lap(self) -> str:
        now = time.monotonic()
        gap, self.last = now - self.last, now
        return f"{gap:.1f} с"

    @property
    def total(self) -> float:
        return time.monotonic() - self.start
