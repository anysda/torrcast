"""Правило compose; используют модели и фасады разбора имён."""

from __future__ import annotations

from collections import Counter

from torrcast.domain._name_data import _CYRILLIC
from torrcast.domain.alias_slugs import _alias_slugs
from torrcast.domain.by_majority import by_majority
from torrcast.domain.kind import Kind
from torrcast.domain.part_number import part_number
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _compose(kind: Kind, year: int | None, group: list[Release], also: str = "") -> Picture:
    titles = Counter(r.title for r in group if _CYRILLIC.search(r.title))
    title = by_majority(titles or Counter(r.title for r in group))
    originals = Counter(r.original for r in group if r.original)
    parts = Counter(n for r in group if (n := part_number(r.title)) is not None)
    original = by_majority(originals) if originals else None
    return Picture(
        title=title,
        year=year,
        kind=kind,
        original=original,
        part=min(parts, key=lambda n: (-parts[n], n)) if parts else None,
        also=also,
        aliases=_alias_slugs(group, title, original),
        releases=group,
    )


__all__ = ["_compose"]
