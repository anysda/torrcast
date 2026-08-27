"""Правило by subtitle; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify
from torrcast.domain.subtitles import _subtitles


def _by_subtitle(query: str, pictures: list[Picture]) -> list[Picture]:
    wanted = slugify(query)
    if not wanted:
        return []
    items = [p for p in pictures if wanted in _subtitles(p)]
    items.sort(
        key=lambda p: (
            p.sort_year is None,
            p.sort_year or 0,
            p.year is None,
            p.part or 99,
            -len(p.releases),
            p.title,
        )
    )
    return items


__all__ = ["_by_subtitle"]
