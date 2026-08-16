"""Описывает источник диапазонов байтов для чистого разбора контейнера."""

from typing import Protocol


class RangeReader(Protocol):
    """Даёт байты и накопленную цену чтения без знания транспорта."""

    taken: int
    requests: int

    def read(self, offset: int, size: int) -> bytes: ...
