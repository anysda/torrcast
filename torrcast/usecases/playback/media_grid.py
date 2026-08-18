"""Сетка сегментов в объёме, который нужен показу: границы кусков и опорные кадры.

Строит её медиатракт (:func:`grid_for` композиционного корня), а показ по ней считает
всё, что говорит о времени, и отдаёт её упаковке, прогреву и кодировщику.
"""

from __future__ import annotations

from typing import Protocol

from torrcast.ports.feed_grid import FeedGrid
from torrcast.ports.warm_environment import WarmGrid


class MediaGrid(FeedGrid, WarmGrid, Protocol):
    """Одна сетка на весь показ: та же в манифесте, та же в команде ffmpeg.

    Наследует оба узких договора нарочно. Показ - единственное место, где сетка ходит
    сразу к трём потребителям: подача потока читает её как :class:`FeedGrid`, прогрев -
    как :class:`WarmGrid`, а приёмнику от неё нужна одна ручка (:meth:`after`). Пока
    договор звался `Any`, никакой из трёх не был назван вовсе.
    """

    def after(self, seconds: float) -> float:
        """Граница ближайшего куска ПОСЛЕ этой секунды: ею меряет прыжки приёмник."""
