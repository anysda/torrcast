"""Модель файла раздачи, распознанного как эпизод сериала."""

from dataclasses import dataclass

from torrcast.domain.episode import Episode

__all__ = ["EpisodeFile"]


@dataclass(frozen=True, slots=True)
class EpisodeFile:
    """Индекс и имя торрент-файла вместе с номером сезона и серии."""

    index: int
    season: int
    episode: int
    name: str
    size: int = 0

    @property
    def at(self) -> Episode:
        return Episode(self.season, self.episode)
