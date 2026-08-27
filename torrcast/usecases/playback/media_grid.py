"""Сетка сегментов в объёме, который нужен показу: границы кусков и опорные кадры.

Строит её медиатракт (:func:`grid_for` композиционного корня), а показ по ней считает
всё, что говорит о времени, и отдаёт её упаковке, прогреву и кодировщику.
"""

from __future__ import annotations

from typing import Protocol

from torrcast.domain.film_keys import FilmKeys
from torrcast.ports.feed_grid import FeedGrid
from torrcast.ports.warm_environment.warm_grid import WarmGrid


class MediaGrid(WarmGrid, FeedGrid, Protocol):
    """Одна сетка на весь показ: та же в манифесте, та же в команде ffmpeg.

    Наследует оба узких договора нарочно. Показ - единственное место, где сетка ходит
    сразу к трём потребителям: подача потока читает её как :class:`FeedGrid`, прогрев -
    как :class:`WarmGrid`, а приёмнику от неё нужна одна ручка (:meth:`after`). Пока
    договор звался `Any`, никакой из трёх не был назван вовсе.
    """

    @property
    def keys(self) -> FilmKeys | None:
        """Карта, по которой считается ВЕС куска; ``None`` - карты нет вовсе.

        🔴 Не «карта, по которой стоят границы»: про границы отвечает
        :attr:`~torrcast.ports.warm_environment.warm_grid.WarmGrid.on_keys`, и на ровной сетке
        карта тоже бывает - снятая, но отвергнутая как сетка. По ней кодировщик тяжёлых
        кусков строит профиль тяжести (:func:`torrcast.usecases.playback._recoder._profile`), и
        спрашивает он её у сетки, а не у полки: карта известна ровно в момент постройки.
        """

    def after(self, seconds: float) -> float:
        """Граница ближайшего куска ПОСЛЕ этой секунды: ею меряет прыжки приёмник."""
