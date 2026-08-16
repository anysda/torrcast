"""Правило franchises; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.franchise_item_key import _franchise_item_key
from torrcast.domain.picture import Picture


def franchises(pictures: list[Picture]) -> dict[str, list[Picture]]:
    grouped: dict[str, list[Picture]] = {}
    for picture in pictures:
        grouped.setdefault(picture.franchise, []).append(picture)
    for items in grouped.values():
        items.sort(key=_franchise_item_key)
    return grouped


__all__ = ["franchises"]
