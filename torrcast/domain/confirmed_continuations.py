"""Правило confirmed continuations; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.menu_order import menu_order
from torrcast.domain.picture import Picture


def confirmed_continuations(
    groups: dict[str, list[Picture]], key: str, franchise: list[Picture]
) -> list[Picture]:
    base = [p for p in franchise if p.kind != "other"]
    roots = {franchise_key(p.original) for p in base if p.original}
    roots.discard("")
    anchor = min((p.year for p in base if p.year is not None), default=None)
    if not roots or anchor is None:
        return []
    found: list[Picture] = []
    for grouped_key, items in groups.items():
        if grouped_key == key or not grouped_key.startswith(f"{key}-"):
            continue
        if grouped_key.startswith(f"{key}-и-"):
            continue
        found += [
            p
            for p in items
            if p.kind != "other"
            and p.year is not None
            and (p.year >= anchor)
            and p.original
            and (franchise_key(p.original) in roots)
        ]
    if not found:
        return []
    was = menu_order(base)[0].key
    while found:
        top = menu_order(base + found)[0].key
        if top == was:
            break
        trimmed = [p for p in found if p.key != top]
        if len(trimmed) == len(found):
            return []
        found = trimmed
    return found


__all__ = ["confirmed_continuations"]
