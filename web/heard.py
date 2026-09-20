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
    #: Инфохэш этой раздачи: «Играть» зовёт показ ею, и номера дорожек относятся к ней.
    release: str = ""
    #: 🔴 TC-1303. Раздача - запасной ход: языка зрителя не нашлось ни у кого, играет то,
    #: что есть (:attr:`torrcast.usecases.select._prep._Prep.voice_fallback`). Карточка
    #: обязана сказать это явной строкой (:func:`web.release_keys.release_keys`), а не
    #: оставить звук неожиданностью.
    fallback: bool = False

    @property
    def default(self) -> int:
        """Дорожка, которую показ взял бы без выбора: лестница языка ПРОЦЕССА, как у
        ``cast voices``, а не страницы - играет процесс."""
        return self.media.default_track(self.native)


__all__ = ["Heard"]
