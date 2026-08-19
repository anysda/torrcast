"""Правило alt query; используют модели и фасады разбора имён."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from torrcast.domain._name_data.data_1 import _CYRILLIC
from torrcast.domain.akin import _akin
from torrcast.domain.franchise_name import franchise_name
from torrcast.domain.release import Release
from torrcast.domain.slugify import slugify
from torrcast.domain.transliterate import transliterate


def alt_query(query: str, releases: Iterable[Release], known: str = "", native: str = "") -> str:
    wanted = slugify(query)
    if not _CYRILLIC.search(query):
        known = known.strip()
        if known and (not _CYRILLIC.search(known)) and (slugify(known) != wanted):
            return known
        native = native.strip()
        return native if _CYRILLIC.search(native) and slugify(native) != wanted else ""
    if known and (not _CYRILLIC.search(known)) and (slugify(known) != wanted):
        return known.strip()
    pool = list(releases)
    names = Counter(
        franchise_name(original)
        for release in pool
        if (original := release.original) and _akin(wanted, slugify(release.title))
    )
    for name, _count in names.most_common():
        if name and (not _CYRILLIC.search(name)) and (slugify(name) != wanted):
            return name
    words = slugify(query).split("-")
    return transliterate(query) if pool or len(words) == 1 else ""


__all__ = ["alt_query"]
