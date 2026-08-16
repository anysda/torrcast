"""Правило both words; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify
from torrcast.domain.words import _words


def _both_words(picture: Picture) -> set[str]:
    return _words(slugify(picture.title)) | _words(slugify(picture.original or ""))


__all__ = ["_both_words"]
