"""Правило by subtitle; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify
from torrcast.domain.subtitles import _subtitles


def _by_subtitle(query: str, pictures: list[Picture]) -> list[Picture]:
    wanted = slugify(query)
    if not wanted:
        return []
    # Подписью картину зовут и КУСКОМ: «Kaede to Suzu» при подписи «Kaede to Suzu The
    # Animation». Сличение подписи целиком отвечало пустотой ровно там, где человек назвал
    # картину почти дословно.
    items = [p for p in pictures if any(wanted in slug for slug in _subtitles(p))]
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
