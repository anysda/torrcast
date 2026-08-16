"""Правило reads season; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.franchise_item_key import _franchise_item_key
from torrcast.domain.numbered_season import _numbered_season
from torrcast.domain.picture import Picture


def reads_season(pictures: list[Picture]) -> bool:
    line = [p for p in pictures if p.kind != "other"]
    if not line or any(p.part is not None and (not _numbered_season(p)) for p in line):
        return False
    return min(line, key=_franchise_item_key).kind == "tv"


__all__ = ["reads_season"]
