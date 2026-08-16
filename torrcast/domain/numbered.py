"""Правило numbered; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain._name_data import _ALTERNATIVE_PICTURE_RE, _ALTERNATIVE_TITLE_RE
from torrcast.domain.living_part import _living_part
from torrcast.domain.numbered_line import _numbered_line
from torrcast.domain.picture import Picture
from torrcast.domain.reads_season import reads_season


def _numbered(items: list[Picture], index: int | None) -> list[Picture]:
    if index is None:
        return items
    if reads_season(items):
        return [p for p in items if p.kind == "tv"]
    line = _numbered_line([p for p in items if p.kind != "other"])[0]
    explicit = [p for p in line if p.part == index]
    if explicit:
        best = max(explicit, key=lambda p: len(p.releases))
        alternative = bool(best.releases) and all(
            _ALTERNATIVE_PICTURE_RE.search(r.raw_name)
            or _ALTERNATIVE_TITLE_RE.search(r.raw_name.split(" / ", 1)[0])
            for r in best.releases
        )
        if best.year is not None and (not alternative):
            return [best]
        rival = _living_part(items, line, index, best)
        if rival is not None:
            return [rival]
        return [best]
    if not 1 <= index <= len(line):
        return []
    found = line[index - 1]
    return [] if found.part is not None else [found]


__all__ = ["_numbered"]
