"""Правило outside numbering; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.numbered_line import _numbered_line
from torrcast.domain.picture import Picture


def outside_numbering(pictures: list[Picture]) -> set[str]:
    return {p.key for p in _numbered_line(pictures)[1]}


__all__ = ["outside_numbering"]
