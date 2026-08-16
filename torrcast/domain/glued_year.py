"""Правило glued year; используют модели и фасады разбора имён."""

from __future__ import annotations

from collections import Counter

from torrcast.domain.kind import Kind
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _glued_year(kind: Kind, merged: list[Picture], releases: list[Release]) -> int | None:
    dated = [r.year for r in releases if r.year is not None]
    if kind != "tv" and dated:
        counted = Counter(dated)
        return min(counted, key=lambda year: (-counted[year], year))
    return min((p.year for p in merged if p.year is not None), default=None)


__all__ = ["_glued_year"]
