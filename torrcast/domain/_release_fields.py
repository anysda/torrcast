"""Поля релиза: то, что вычитано из имени раздачи и из ответа индексера.

Наследует их :class:`torrcast.domain.release.Release`, и только он.
"""

from __future__ import annotations

from dataclasses import dataclass

from torrcast.domain.kind import Kind


@dataclass(frozen=True, slots=True)
class _ReleaseFields:
    """Разобранное имя раздачи и её цифры: вес, сиды, магнит, откуда приехала."""

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
