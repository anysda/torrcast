"""Правило Release; используют модели и фасады разбора имён."""

from __future__ import annotations

import re
from dataclasses import dataclass

from torrcast.domain._name_data import (
    _AVI_RE,
    _DUBBED,
    _EXTRAS_RE,
    _EXTRAS_SURE_RE,
    _FOREIGN_DUB_RE,
    _HD_SOURCES,
    _RU_AUDIO_RE,
    _RU_EXT_RE,
    _RU_STUDIO_RE,
    _SD_SOURCES,
    _STEREO_LAYOUT_RE,
    _STEREO_RE,
    _SUB_MENTION_RE,
    _TWO_D_RE,
    _WITH_EXTRAS_RE,
)
from torrcast.domain.anime_indexer import anime_indexer
from torrcast.domain.episode import Episode
from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.kind import Kind
from torrcast.domain.looks_anime import looks_anime
from torrcast.domain.parse_voices import _parse_voices
from torrcast.domain.slugify import slugify


@dataclass(frozen=True, slots=True)
class Release:
    raw_name: str
    title: str
    original: str | None = None
    aliases: tuple[str, ...] = ()
    year: int | None = None
    quality: str | None = None
    codec: str | None = None
    source: str | None = None
    hdr: bool = False
    voices: tuple[str, ...] = ()
    season: int | None = None
    episode: int | None = None
    seasons: tuple[int, ...] = ()
    episodes: tuple[int, ...] = ()
    size: int = 0
    seeders: int = 0
    magnet: str = ""
    indexer: str = ""
    kind: Kind = "movie"
    copies: int = 1
    indexers: tuple[str, ...] = ()
    names: tuple[str, ...] = ()
    collection: bool = False

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
    def stereoscopic(self) -> bool:
        if _STEREO_LAYOUT_RE.search(self.raw_name):
            return True
        tail = self.untitled
        return bool(re.search("\\b3д\\b", self.raw_name, re.IGNORECASE)) or (
            not _TWO_D_RE.search(tail) and bool(_STEREO_RE.search(tail))
        )

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

    @property
    def extras_mark(self) -> str:
        """Метка приложения, сработавшая в зоне пометок; пусто - метки нет.

        Метка, перед которой стоит «+», приложением раздачу не делает: «фильм + доп
        материалы» - это фильм, к которому приложено, а не приложение само по себе.
        """
        tail = self.untitled
        for found in _EXTRAS_RE.finditer(tail):
            if not _WITH_EXTRAS_RE.search(tail[: found.start()]):
                return found.group(0)
        return ""

    @property
    def extras(self) -> bool:
        return bool(self.extras_mark)

    @property
    def extras_sure(self) -> bool:
        return self.extras and bool(_EXTRAS_SURE_RE.search(self.untitled))

    @property
    def untitled(self) -> str:
        """Имя раздачи без названия картины: зона пометок, по которой судят метки."""
        tail = self.raw_name
        for name in (self.title, self.original, *self.aliases):
            if name:
                tail = re.sub(f"(?<!\\w){re.escape(name)}(?!\\w)", " ", tail, flags=re.IGNORECASE)
        return tail

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
