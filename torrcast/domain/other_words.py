"""Правило other words; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify


def other_words(query: str, picture: Picture | None) -> str:
    if picture is None:
        return ""
    wanted = slugify(query)
    keys = [picture.franchise]
    if picture.original:
        keys.append(franchise_key(picture.original))
    if any(wanted in key or key in wanted for key in keys):
        return ""
    return picture.title


__all__ = ["other_words"]
