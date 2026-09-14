"""Что узнал фоновый отбор о раздаче: паспорт и студии (:mod:`web.voice_lookup`)."""

from __future__ import annotations

from dataclasses import dataclass

from torrcast.domain.media import Media
from torrcast.domain.studio import Studio


@dataclass(frozen=True)
class Heard:
    """Паспорт выбранной раздачи и всё, что нужно подписать его дорожки."""

    media: Media
    native: bool
    studios: tuple[Studio, ...]

    @property
    def default(self) -> int:
        """Дорожка, которую показ взял бы без выбора: лестница языка ПРОЦЕССА, как у
        ``cast voices``, а не страницы - играет процесс."""
        return self.media.default_track(self.native)


__all__ = ["Heard"]
