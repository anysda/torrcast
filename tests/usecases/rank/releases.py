"""Заготовки раздачи и паспорта для зеркал пакета ранжирования.

Отдельным файлом, а не фикстурой: зеркала спрашивают правила напрямую, без стенда, и
собирать одну и ту же раздачу в каждом из них значило бы разводить сорок редакций.
"""

from __future__ import annotations

from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.kind import Kind
from torrcast.domain.media import Media
from torrcast.domain.release import Release

GB = 1024**3
#: Та же прикидка «фильм это два часа», с которой отбор живёт, пока справка молчит.
RUNTIME = 7200.0


def rel(
    name: str = "Кино / Movie (1999) BDRip 1080p",
    *,
    title: str = "Кино",
    quality: str | None = "1080p",
    codec: str | None = "H.264",
    hdr: bool = False,
    source: str | None = "BDRip",
    voices: tuple[str, ...] = (),
    size_gb: float = 8.0,
    seeders: int = 100,
    kind: Kind = "movie",
    season: int | None = None,
    episode: int | None = None,
    seasons: tuple[int, ...] = (),
    episodes: tuple[int, ...] = (),
    collection: bool = False,
) -> Release:
    """Раздача с предсказуемыми полями: тест меняет ровно то, что он и меряет."""
    return Release(
        raw_name=name,
        title=title,
        year=1999,
        quality=quality,
        codec=codec,
        hdr=hdr,
        source=source,
        voices=voices,
        size=int(size_gb * GB),
        seeders=seeders,
        magnet=f"magnet-{name}",
        kind=kind,
        season=season,
        episode=episode,
        seasons=seasons,
        episodes=episodes,
        collection=collection,
    )


def track(index: int = 0, language: str | None = "rus", title: str | None = "Дубляж") -> AudioTrack:
    """Звуковая дорожка паспорта: язык тегом, вид перевода заголовком."""
    return AudioTrack(index=index, language=language, title=title)


def media(
    height: int = 1080,
    width: int = 1920,
    *,
    tracks: tuple[AudioTrack, ...] = (),
    field_order: str | None = None,
) -> Media:
    """Паспорт ffprobe: кадр, развёртка и звуковые дорожки."""
    return Media(
        duration=RUNTIME, height=height, width=width, tracks=tracks, field_order=field_order
    )
