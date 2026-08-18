"""Ровная карта опорных кадров и сетка по ней: общее для зеркал пакета перекодирования."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.stream_pack.grid import Grid

if TYPE_CHECKING:
    from torrcast.domain.film_keys import FilmKeys


def keys(duration: float = 300.0, gop: float = 2.0, rate: float = 2.0e6) -> FilmKeys:
    """Карта с опорным кадром каждые ``gop`` секунд и ровным весом ``rate`` байт в секунду."""
    from torrcast.domain.film_keys import FilmKeys

    at = [round(number * gop, 3) for number in range(int(duration / gop) + 1)]
    return FilmKeys(duration=duration, at=at, offset=[int(t * rate) for t in at], kind="mkv")


def grid(duration: float = 300.0, gop: float = 2.0, step: float = 10.0) -> Grid:
    """Сетка по опорным кадрам той же карты."""
    return Grid.on_keyframes(keys(duration, gop).at, duration, step)
