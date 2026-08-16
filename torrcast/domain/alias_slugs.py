"""Правило alias slugs; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.release import Release
from torrcast.domain.slugify import slugify


def _alias_slugs(group: list[Release], title: str, original: str | None) -> tuple[str, ...]:
    known = {slugify(title), slugify(original or "")}
    found = {slug for r in group for name in r.aliases if (slug := slugify(name))}
    return tuple(sorted(found - known))


__all__ = ["_alias_slugs"]
