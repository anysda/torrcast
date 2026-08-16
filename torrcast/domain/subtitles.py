"""Правило subtitles; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain._name_data import _SUBTITLE_RE
from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify


def _subtitles(picture: Picture) -> set[str]:
    found = set()
    for title in (picture.title, picture.original or ""):
        parts = _SUBTITLE_RE.split(title.strip(), maxsplit=1)
        if len(parts) == 2 and (slug := slugify(parts[1])):
            found.add(slug)
    return found


__all__ = ["_subtitles"]
