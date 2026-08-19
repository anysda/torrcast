"""Правило chapter of; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain._name_data.data_2 import _CHAPTER_RE, _PART_NUMBER_RE, _ROMAN
from torrcast.domain.slugify import slugify


def _chapter_of(title: str) -> tuple[str, int] | None:
    match = _PART_NUMBER_RE.match(title.strip())
    if not match:
        return None
    head = title[: match.start(1)].rstrip(" ,-")
    if not _CHAPTER_RE.search(head):
        return None
    base = slugify(_CHAPTER_RE.sub("", head).rstrip(" ,-:."))
    token = match.group(1).lower()
    number = int(token) if token.isdigit() else _ROMAN.get(token)
    return (base, number) if base and number is not None else None


__all__ = ["_chapter_of"]
