"""Правило living part; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.picture import Picture


def _living_part(
    items: list[Picture], line: list[Picture], index: int, claimant: Picture
) -> Picture | None:
    anchor = max(
        (p.year for p in line if p.part is not None and p.part < index and (p.year is not None)),
        default=None,
    )
    if anchor is None:
        return None
    newer = [
        p
        for p in items
        if p.kind != "other"
        and (not p.collection)
        and (p.part is None)
        and (p.year is not None)
        and (p.year > anchor)
    ]
    rival = max(newer, key=lambda p: len(p.releases), default=None)
    if rival is not None and len(rival.releases) > len(claimant.releases):
        return rival
    return None


__all__ = ["_living_part"]
