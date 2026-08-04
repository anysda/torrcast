"""Парсер имён раздач и кластеризация франшиз.

Метаданных извне нет: всё, что мы знаем о картине, добывается из имени раздачи
(§3 ТЗ). Модуль решает три задачи:

1. имя раздачи → :class:`Release` (название, оригинал, год, качество, кодек, озвучки);
2. набор релизов → :class:`Picture`-кластеры (франшиза = общее каноническое
   название, сортировка по году даёт нумерацию, §2.2);
3. разбор эпизодов ``s01e05`` / ``2x5`` / «2 сезон 5 серия» (§2.4).

Полноценный парсер обкатывается на корпусе реальной выдачи трекеров (§7, этап 1);
здесь — рабочий каркас с уже закреплёнными в тестах правилами.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Final, Literal

__all__ = [
    "Episode",
    "Picture",
    "Release",
    "cluster",
    "parse_episode",
    "parse_release_name",
    "slugify",
    "split_franchise_index",
]

Kind = Literal["movie", "tv"]

#: Качество → нормальная форма.
_QUALITY_RE: Final = re.compile(r"\b(2160p|1080p|720p|480p|4k|uhd)\b", re.IGNORECASE)
_YEAR_RE: Final = re.compile(r"\b(19\d{2}|20\d{2})\b")
_HEVC_RE: Final = re.compile(r"\b(hevc|h\.?265|x265)\b", re.IGNORECASE)
_H264_RE: Final = re.compile(r"\b(avc|h\.?264|x264)\b", re.IGNORECASE)

#: Маркеры озвучки в русских раздачах. Порядок задаёт приоритет показа.
_VOICE_MARKERS: Final[tuple[tuple[str, str], ...]] = (
    ("дубляж", "Дубляж"),
    ("dub", "Дубляж"),
    ("многоголос", "Многоголосый"),
    ("mvo", "Многоголосый"),
    ("двухголос", "Двухголосый"),
    ("dvo", "Двухголосый"),
    ("авторск", "Авторский"),
    ("avo", "Авторский"),
    ("субтитр", "Субтитры"),
    ("original", "Original"),
    ("orig", "Original"),
)

_SEASON_EPISODE_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bs\s*(?P<season>\d{1,2})\s*[.\-_ ]?\s*e\s*(?P<episode>\d{1,3})\b", re.IGNORECASE),
    re.compile(r"\b(?P<season>\d{1,2})\s*[xх]\s*(?P<episode>\d{1,3})\b", re.IGNORECASE),
    re.compile(
        r"(?P<season>\d{1,2})\s*сезон\D{0,12}?(?P<episode>\d{1,3})\s*сери",
        re.IGNORECASE,
    ),
)

#: Хвост технических тегов — всё, что после них, к названию не относится.
_TECH_TAIL_RE: Final = re.compile(
    r"\b(bdrip|bd-?remux|remux|web-?dl|web-?rip|hdrip|dvdrip|hdtv|blu-?ray|uhd|"
    r"2160p|1080p|720p|480p|4k|hevc|h\.?26[45]|x26[45]|avc|ac3|dts|aac|flac)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Release:
    """Одна раздача после разбора имени."""

    raw_name: str
    title: str
    original: str | None = None
    year: int | None = None
    quality: str | None = None
    codec: str | None = None
    voices: tuple[str, ...] = ()
    size: int = 0
    seeders: int = 0
    magnet: str = ""
    indexer: str = ""
    kind: Kind = "movie"

    @property
    def is_hevc(self) -> bool:
        """HEVC показываем с пометкой ⚠ и никогда не берём по умолчанию (§3)."""
        return self.codec == "HEVC"

    @property
    def slug(self) -> str:
        return slugify(self.title)


@dataclass(slots=True)
class Picture:
    """Картина — кластер релизов с общим каноническим названием и годом."""

    title: str
    year: int | None
    kind: Kind = "movie"
    releases: list[Release] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Ключ состояния: ``<тип>:<slug>:<год>`` (§4 ТЗ)."""
        return f"{self.kind}:{slugify(self.title)}:{self.year if self.year else '0'}"

    @property
    def best_release(self) -> Release | None:
        """Дефолт меню: самый обсиженный H.264-релиз, HEVC — в конце (§3)."""
        if not self.releases:
            return None
        return sorted(self.releases, key=lambda r: (r.is_hevc, -r.seeders))[0]


@dataclass(frozen=True, slots=True)
class Episode:
    """Сезон и серия."""

    season: int
    episode: int

    def __str__(self) -> str:
        return f"s{self.season}e{self.episode}"


def slugify(text: str) -> str:
    """Привести название к ключу состояния: нижний регистр, дефисы, без мусора.

    Кириллица сохраняется — ключи из §4 ТЗ русские (``movie:матрица:1999``).
    """
    normalized = unicodedata.normalize("NFKC", text).casefold().replace("ё", "е")
    cleaned = re.sub(r"[^0-9a-zа-я]+", "-", normalized)
    return cleaned.strip("-")


def split_franchise_index(query: str) -> tuple[str, int | None]:
    """Отделить хвостовой номер франшизы: ``«матрица 2»`` → ``("матрица", 2)``.

    Номер — позиция в отсортированной по году франшизе, а не часть названия
    (§2.2). Год (четыре цифры) номером не считается.
    """
    match = re.search(r"^(?P<name>.+?)\s+(?P<index>\d{1,2})$", query.strip())
    if not match:
        return query.strip(), None
    return match.group("name").strip(), int(match.group("index"))


def parse_episode(text: str) -> Episode | None:
    """Вытащить ``sNeM`` из строки: ``s02e05``, ``2x5``, «2 сезон 5 серия»."""
    for pattern in _SEASON_EPISODE_RES:
        match = pattern.search(text)
        if match:
            return Episode(int(match.group("season")), int(match.group("episode")))
    return None


def parse_release_name(name: str) -> Release:
    """Разобрать имя раздачи в структуру.

    Типовая русская раздача: ``«Матрица / The Matrix (1999) BDRip 1080p»``.
    Название до слэша — русское, после — оригинал.
    """
    year_match = _YEAR_RE.search(name)
    year = int(year_match.group(1)) if year_match else None

    head = name[: year_match.start()] if year_match else name
    head = _TECH_TAIL_RE.split(head)[0]
    head = head.strip(" .-_[]()|")

    title, original = _split_titles(head)

    quality_match = _QUALITY_RE.search(name)
    quality = _normalize_quality(quality_match.group(1)) if quality_match else None

    codec: str | None = None
    if _HEVC_RE.search(name):
        codec = "HEVC"
    elif _H264_RE.search(name):
        codec = "H.264"

    return Release(
        raw_name=name,
        title=title,
        original=original,
        year=year,
        quality=quality,
        codec=codec,
        voices=_parse_voices(name),
        kind="tv" if parse_episode(name) is not None else "movie",
    )


def cluster(releases: list[Release]) -> list[Picture]:
    """Сгруппировать релизы в картины и отсортировать франшизу по году.

    Кластер = общий slug канонического названия и год; порядок в списке —
    хронологический, он же нумерация франшизы (§2.2).
    """
    buckets: dict[tuple[str, int | None], Picture] = {}
    for release in releases:
        key = (release.slug, release.year)
        picture = buckets.get(key)
        if picture is None:
            picture = Picture(title=release.title, year=release.year, kind=release.kind)
            buckets[key] = picture
        picture.releases.append(release)
    return sorted(buckets.values(), key=lambda p: (p.year is None, p.year or 0, p.title))


def _split_titles(head: str) -> tuple[str, str | None]:
    """Разделить ``«Матрица / The Matrix»`` на русское и оригинальное название."""
    parts = [p.strip() for p in head.split("/") if p.strip()]
    if not parts:
        return head.strip(), None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]


def _normalize_quality(value: str) -> str:
    lowered = value.lower()
    if lowered in {"4k", "uhd"}:
        return "2160p"
    return lowered


def _parse_voices(name: str) -> tuple[str, ...]:
    """Собрать маркеры озвучки в порядке приоритета, без повторов."""
    lowered = name.casefold()
    found: list[str] = []
    for marker, label in _VOICE_MARKERS:
        if marker in lowered and label not in found:
            found.append(label)
    return tuple(found)
