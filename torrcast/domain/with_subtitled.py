"""Правило with subtitled; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.by_subtitle import _by_subtitle
from torrcast.domain.picture import Picture


def _with_subtitled(
    items: list[Picture], name: str, pictures: list[Picture], index: int | None
) -> list[Picture]:
    if index is not None or not items:
        return items
    keys = {p.key for p in items}
    return items + [p for p in _by_subtitle(name, pictures) if p.key not in keys]


__all__ = ["_with_subtitled"]
