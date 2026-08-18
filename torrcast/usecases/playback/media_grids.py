"""Завод сетки сегментов: карта опорных кадров файла плюс наши пороги веса.

Кладёт его композиционный корень (:mod:`torrcast.runtime.wire`) под именем ``grid_for``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from torrcast.usecases.playback.media_grid import MediaGrid


class MediaGrids(Protocol):
    """Чем показ строит сетку - и ничего сверх того."""

    def __call__(
        self,
        source_url: str,
        duration: float,
        step: float = ...,
        on_keys: bool = ...,
        say: Callable[[str], None] | None = ...,
        delivered_mbit: float = 0.0,
        ceiling_mbit: float = 0.0,
        fixed_mbit: float = 0.0,
        cap: float = ...,
    ) -> MediaGrid:
        """Сетка для конкретного файла: по опорным кадрам, если карту удалось снять."""
