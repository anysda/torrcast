"""Часы старта показа: сколько прошло от команды до картинки на экране.
Заводят их команда показа и цикл юнита, а называет число строка запуска.
"""

from __future__ import annotations

__all__ = ["_Clock"]

import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class _Clock:
    """Старт показа: холодный стоит 15–30 с, и цифра должна быть видна глазами."""

    start: float = field(default_factory=time.monotonic)

    @property
    def total(self) -> float:
        return time.monotonic() - self.start
