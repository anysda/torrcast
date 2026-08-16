"""Правило franchise item key; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.picture import Picture


def _franchise_item_key(picture: Picture) -> tuple[bool, int, int, int, str]:
    return (
        picture.year is None,
        picture.year or 0,
        picture.part or 99,
        -len(picture.releases),
        picture.title,
    )


__all__ = ["_franchise_item_key"]
