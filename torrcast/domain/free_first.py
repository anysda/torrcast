"""Правило free first; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify


def _free_first(rest: list[Picture], numbered: list[Picture]) -> Picture | None:
    roots = {franchise_key(p.original) for p in numbered if p.original}
    titled = [
        p
        for p in rest
        if p.kind != "other"
        and (
            slugify(p.title) == p.franchise
            or (p.original is not None and franchise_key(p.original) in roots)
        )
    ]
    if not titled:
        return None
    anchor = min((p.year for p in numbered if p.year is not None), default=None)
    if anchor is None:
        return titled[0]
    early = [p for p in titled if p.year is not None and p.year < anchor and (not p.collection)]
    if not early:
        return titled[0]
    return max(early, key=lambda p: (len(p.releases), -(p.year or 0)))


__all__ = ["_free_first"]
