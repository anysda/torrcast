"""Завод решения о ТОЧЕЧНОМ перекоде тяжёлого куска: тот же кадр, ниже битрейт.

Кладёт его композиционный корень (:mod:`torrcast.runtime.wire`) под именем ``Encode``.
"""

from __future__ import annotations

from typing import Protocol

from torrcast.ports.recode.encoding import Encoding


class SpotEncodings(Protocol):
    """Чем показ заводит решение для кодировщика тяжёлых кусков."""

    def __call__(self, *, preset: str = ..., mbit: float = ...) -> Encoding:
        """Решение по настройкам показа: пресет и цель по битрейту."""
