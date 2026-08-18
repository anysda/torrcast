"""Профиль тяжести фильма: сколько Мбит/с уедет на ТВ в каждом сегменте сетки.

Считает его медиатракт (:class:`torrcast.adapters.recode.weights.Weights`) по карте
опорных кадров, а показ по нему решает, нужен ли кодировщик тяжёлых кусков.
"""

from __future__ import annotations

from typing import Protocol


class HeavyProfile(Protocol):
    """Вес каждого куска, посчитанный до всякой упаковки и без единого запроса к рою."""

    @property
    def container(self) -> float:
        """Средний битрейт контейнера по карте, Мбит/с - тот же, что у файла целиком."""
