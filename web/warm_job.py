"""Что греет рука прогрева записей (:mod:`web.record_warm`)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WarmJob:
    """Что греть: раздача записи, адрес файла, закладка и имя файла (контейнер)."""

    magnet: str
    source: str
    at: float
    name: str

    @property
    def mark(self) -> tuple[str, str, int]:
        """Прогретое узнаётся по файлу и секунде закладки: сдвинулась - греть снова."""
        return self.magnet, self.source, round(self.at)
