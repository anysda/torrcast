"""Правило alt query; используют модели и фасады разбора имён."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from torrcast.domain._name_data.data_1 import _CYRILLIC
from torrcast.domain.akin import _akin
from torrcast.domain.catalogs.tongue import EN, tongue
from torrcast.domain.franchise_name import franchise_name
from torrcast.domain.release import Release
from torrcast.domain.romaji import romaji
from torrcast.domain.slugify import slugify
from torrcast.domain.transliterate import transliterate


def alt_query(query: str, releases: Iterable[Release], known: str = "", native: str = "") -> str:
    wanted = slugify(query)
    if not _CYRILLIC.search(query):
        known = known.strip()
        if known and (not _CYRILLIC.search(known)) and (slugify(known) != wanted):
            return known
        native = native.strip()
        if _CYRILLIC.search(native) and slugify(native) != wanted:
            return native
        pool = list(releases)
        if (
            tongue() == EN
            and len(query.split()) == 1
            and any((release.original or "").casefold().startswith("the ") for release in pool)
        ):
            return f"The {query.strip()}"
        return ""
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
    if pool or len(words) == 1:
        return transliterate(query)
    # Многословное имя вслепую транслитерировать нечем - кроме случая, когда оно само
    # уже написано латиницей по смыслу: японское имя кириллицей раскладывается на моры
    # целиком, и тогда второй заход идёт не побуквенным транслитом, а по Хепбёрну.
    return romaji(query)


__all__ = ["alt_query"]
