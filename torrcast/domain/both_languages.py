"""Правило both languages; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.kindred import _kindred
from torrcast.domain.picture import Picture


def _both_languages(
    groups: dict[str, list[Picture]], aliases: dict[str, str], key: str
) -> list[Picture]:
    items = list(groups[key])
    base = list(items)
    twins = {aliases.get(key, "")} | {a for a, target in aliases.items() if target == key}
    seen = {id(p) for p in items}
    for twin in twins:
        if not twin or twin == key:
            continue
        fresh = [p for p in groups.get(twin, []) if id(p) not in seen and _kindred(p, base)]
        items += fresh
        seen |= {id(p) for p in fresh}
    items.sort(key=lambda p: (p.year is None, p.year or 0, p.part or 99, -len(p.releases), p.title))
    return items


__all__ = ["_both_languages"]
