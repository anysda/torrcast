"""Диапазоны файла с диска: тот же договор чтения, что у боевого HTTP, только без роя."""

from __future__ import annotations

from pathlib import Path


class DiskRangeReader:
    """Читатель диапазонов с диска: рою тут взяться неоткуда.

    Договор тот же, что у боевого :class:`~torrcast.adapters.frames.http_range_reader.
    HttpRangeReader`: байты по смещению и накопленная цена чтения. Стенду медиатракта
    нужен настоящий контейнер, а не настоящая сеть - карта обязана сниматься с тех же
    байтов, по которым потом пройдёт ffmpeg.
    """

    def __init__(self, url: str) -> None:
        self.url = url
        self.taken = 0
        self.requests = 0

    def read(self, offset: int, size: int) -> bytes:
        data = Path(self.url).read_bytes()[offset : offset + size]
        self.taken += len(data)
        self.requests += 1
        return data
