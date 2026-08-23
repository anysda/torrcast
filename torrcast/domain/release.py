"""Правило Release; используют модели и фасады разбора имён."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

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

#: Как кодек зовётся в имени раздачи и как его зовёт профиль приёмника
#: (:meth:`torrcast.domain.profile.Profile.verdict`). Имя молчит - ключа нет, и приговор
#: достаётся умолчанию профиля.
_PROFILE_CODECS: Final = {"HEVC": "hevc", "H.264": "h264", "MPEG-4": "mpeg4", "AV1": "av1"}
#: Сколько бит на цвет обещает пометка HDR: и HDR10, и Dolby Vision - это десять,
#: восьмибитного HDR не бывает.
_HDR_DEPTH: Final = 10


@dataclass(frozen=True, slots=True)
class Release(_ReleaseMarks):
    """Раздача целиком: качество картинки, язык звука, серии и ключи франшизы."""

    @property
    def is_hevc(self) -> bool:
        return self.codec == "HEVC"

    @property
    def named_codec(self) -> str:
        """Кодек, НАЗВАННЫЙ именем раздачи, словами профиля приёмника; пусто - имя молчит.

        Профиль судит кодеки одним ключом (``hevc``, ``h264``), а имя раздачи пишет их
        по-человечески (``HEVC``, ``H.264``), и перевод нужен ровно затем, чтобы вопрос
        «возьмёт ли это приёмник копией» задавался ОДНОЙ функции
        (:func:`torrcast.domain.recodes_whole.recodes_whole`), а не второму списку рядом с ней.

        Пусто - это «имя не сказало», а не «кодека нет»: приговор такому релизу вынесет
        умолчание самого профиля, ровно как выносит его показ.
        """
        return _PROFILE_CODECS.get(self.codec or "", "")

    @property
    def named_depth(self) -> int:
        """Глубина цвета, НАЗВАННАЯ именем раздачи; ноль - имя о ней молчит.

        Пометка HDR - единственное, что имя об этом говорит, и говорит она достаточно:
        и HDR10, и Dolby Vision несут десять бит на цвет по своему определению. Осторожному
        приёмнику этого хватает, чтобы отказаться от копии (:attr:`Profile.copy_depth`), -
        та же беда, что у десятибитного H.264, только названная в имени вслух.

        Ноль тут значит «не спрашивали», а не «восемь»: точную глубину знает ffprobe после
        выбора (:func:`torrcast.domain.color_depth.color_depth`), и спорить с ним имени нечем.
        """
        return _HDR_DEPTH if self.hdr else 0

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
