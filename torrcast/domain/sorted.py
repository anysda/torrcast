"""Правило sorted; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.picture import Picture


def _sorted(pictures: list[Picture]) -> list[Picture]:
    return sorted(pictures, key=lambda p: (p.year is None, p.year or 0, p.title, p.original or ""))


__all__ = ["_sorted"]
