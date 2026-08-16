"""Правило menu order; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.franchise_item_key import _franchise_item_key
from torrcast.domain.numbered_line import _numbered_line
from torrcast.domain.picture import Picture


def menu_order(pictures: list[Picture]) -> list[Picture]:
    picked = [p for p in pictures if not p.collection]
    source = picked or list(pictures)
    keys = {p.franchise for p in source}
    if any(sum(other.startswith(f"{key}-и-") for other in keys) >= 2 for key in keys):
        return sorted(source, key=_franchise_item_key)
    line, tail = _numbered_line(source)
    return line + tail


__all__ = ["menu_order"]
