"""Опорный кадр карты: время, байт и дорожка; зовут оба разбора и сетка сегментов."""

from __future__ import annotations

from typing import NamedTuple


class Point(NamedTuple):
    """Опорный кадр: время от начала фильма, абсолютное смещение в байтах, номер дорожки."""

    at: float
    offset: int
    track: int
