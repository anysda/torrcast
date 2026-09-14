"""Картина офлайн-карты IMDb под прокатным именем: год, тип, оригинал и число голосов."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MapPicture:
    """Строка карты имён вместе с голосами IMDb: чем картину доказывают и кто из тёзок сильнее.

    ``votes`` - число голосов IMDb, ноль значит «не знаем», а не «никто не смотрел»: выгрузка
    рейтингов могла не доехать. ``series`` - сериал в понимании карты (:data:`_TV_KINDS`).
    """

    name: str
    year: int | None
    series: bool
    original: str
    votes: int


__all__ = ["MapPicture"]
