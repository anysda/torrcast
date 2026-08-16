"""Правило by both names; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.both_words import _both_words
from torrcast.domain.one_name_is_enough import _one_name_is_enough
from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify
from torrcast.domain.words import _words


def _by_both_names(query: str, pictures: list[Picture]) -> list[Picture]:
    asked = _words(slugify(query))
    if len(asked) < 2:
        return []
    items = [p for p in pictures if asked <= _both_words(p) and (not _one_name_is_enough(asked, p))]
    items.sort(key=lambda p: (p.year is None, p.year or 0, p.part or 99, -len(p.releases), p.title))
    return items


__all__ = ["_by_both_names"]
