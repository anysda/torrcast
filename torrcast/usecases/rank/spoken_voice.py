"""Запомненный выбор вслух; зовут показ строки состояния и запасной ход при памяти.

Ключ памяти (:attr:`torrcast.domain.entry.Entry.voice`) не двигается ни на байт: чужой
текст (заголовок дорожки из раздачи) остаётся как есть, звучит на языке продукта только
наша запасная подпись (:mod:`torrcast.domain.fallback_track_number`).
"""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.fallback_track_number import fallback_track_number


def spoken_voice(value: str) -> str:
    """Запомненный выбор для печати человеку: чужой текст остаётся как есть, а наша
    запасная подпись (:mod:`torrcast.domain.fallback_track_number`) звучит на языке
    продукта. Ключ памяти при этом не двигается ни на байт - переводится только то,
    что о нём напечатано.
    """
    number = fallback_track_number(value)
    if number is None:
        return value
    return phrase("select.track_number", number=number)
