"""Правило kindred; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.picture import Picture


def _kindred(picture: Picture, base: list[Picture]) -> bool:
    for other in base:
        if picture.kind == other.kind:
            return True
        if picture.year is None or other.year is None or abs(picture.year - other.year) <= 1:
            return True
    return False


__all__ = ["_kindred"]
