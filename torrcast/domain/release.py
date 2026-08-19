"""Правило Release; используют модели и фасады разбора имён."""

from __future__ import annotations

from dataclasses import dataclass

from torrcast.domain._name_data.data_1 import (
    _AVI_RE,
    _DUBBED,
    _HD_SOURCES,
    _RU_AUDIO_RE,
    _SD_SOURCES,
    _SUB_MENTION_RE,
)
from torrcast.domain._name_data.data_2 import _FOREIGN_DUB_RE, _RU_EXT_RE, _RU_STUDIO_RE
from torrcast.domain._release_marks import _ReleaseMarks
from torrcast.domain.anime_indexer import anime_indexer
from torrcast.domain.episode import Episode
from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.looks_anime import looks_anime
from torrcast.domain.parse_voices import _parse_voices
from torrcast.domain.slugify import slugify
from torrcast.domain.studio import Studio
from torrcast.domain.studios_in import studios_in


@dataclass(frozen=True, slots=True)
class Release(_ReleaseMarks):
    """Раздача целиком: качество картинки, язык звука, серии и ключи франшизы."""

    @property
    def is_hevc(self) -> bool:
        return self.codec == "HEVC"

    @property
    def height(self) -> int:
        digits = (self.quality or "").rstrip("pi")
        return int(digits) if digits.isdigit() else 0

    @property
    def interlaced(self) -> bool:
        return bool(self.quality and self.quality.endswith("i"))

    @property
    def prime(self) -> bool:
        if self.codec:
            return self.codec == "H.264"
        return self.height >= 720 or self.source in _HD_SOURCES

    @property
    def quiet(self) -> bool:
        return not self.codec and (not self.height)

    @property
    def dubbed(self) -> bool:
        text = _RU_EXT_RE.sub(
            " ", _FOREIGN_DUB_RE.sub(" ", _SUB_MENTION_RE.sub(" ", self.raw_name))
        )
        if any(v in _DUBBED for v in _parse_voices(text)):
            return True
        return bool(_RU_AUDIO_RE.search(text) or _RU_STUDIO_RE.search(text))

    @property
    def external_dub(self) -> bool:
        return any(_RU_EXT_RE.search(name) for name in self.names or (self.raw_name,))

    @property
    def studios(self) -> tuple[Studio, ...]:
        """Знакомые студии, названные ИМЕНЕМ раздачи, в порядке появления.

        У сезонной раздачи это единственное место, где студия вообще написана: дорожки
        внутри подписаны голым тегом ``rus``, и ни ffprobe, ни таблица озвучек про
        «The Kitchen Russia» не скажут ничего. Судится зона пометок
        (:attr:`untitled`), а не всё имя: название картины бывает тёзкой студии, и
        «Гоблин» в имени фильма - это фильм, а не перевод.
        """
        return studios_in(self.untitled)

    @property
    def anime(self) -> bool:
        if any(anime_indexer(name) for name in (self.indexer, *self.indexers)):
            return True
        return looks_anime(self.raw_name)

    @property
    def dated(self) -> bool:
        return (
            self.codec == "MPEG-4"
            or self.source in _SD_SOURCES
            or bool(_AVI_RE.search(self.raw_name))
        )

    def covers(self, season: int) -> bool:
        if self.seasons:
            return season in self.seasons
        return self.season in (None, season)

    def covers_episode(self, want: Episode) -> bool:
        if not self.covers(want.season):
            return False
        if self.episodes:
            return want.episode in self.episodes
        return self.episode in (None, want.episode)

    @property
    def episode_count(self) -> int:
        if self.episodes:
            return len(self.episodes)
        return 1 if self.episode is not None else 0

    @property
    def collection_count(self) -> int | None:
        if not self.collection:
            return 1
        low = self.raw_name.lower()
        for marker, count in (("дилог", 2), ("трилог", 3), ("trilogy", 3), ("квадролог", 4)):
            if marker in low:
                return count
        return None

    @property
    def slug(self) -> str:
        return slugify(self.title)

    @property
    def franchise(self) -> str:
        return franchise_key(self.title)


__all__ = ["Release"]
