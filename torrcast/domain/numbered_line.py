"""Правило numbered line; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.free_first import _free_first
from torrcast.domain.picture import Picture


def _numbered_line(pictures: list[Picture]) -> tuple[list[Picture], list[Picture]]:
    numbered = sorted(
        (p for p in pictures if p.part is not None and p.kind != "other"),
        key=lambda p: (p.part or 0, p.year is None, p.year or 0, p.title),
    )
    if not numbered:
        return (sorted(pictures, key=lambda p: p.kind == "other"), [])
    rest = [p for p in pictures if p.part is None or p.kind == "other"]
    free = _free_first(rest, numbered) if rest and all(p.part != 1 for p in numbered) else None
    first = [free] if free is not None else []
    tail = [p for p in rest if p is not free]
    return (first + numbered, tail)


__all__ = ["_numbered_line"]
