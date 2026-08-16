"""Правило catalog has name; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify
from torrcast.domain.split_franchise_index import split_franchise_index


def catalog_has_name(query: str, pictures: list[Picture]) -> bool:
    name, _index = split_franchise_index(query)
    wanted = slugify(name)
    if not wanted:
        return False
    for picture in pictures:
        if slugify(picture.title) == wanted:
            return True
        if picture.original and slugify(picture.original) == wanted:
            return True
        if franchise_key(picture.title) == wanted and picture.part in (None, 1):
            return True
        alias_support = sum(
            wanted in {slugify(alias) for alias in release.aliases} for release in picture.releases
        )
        if alias_support >= 2:
            return True
    return False


__all__ = ["catalog_has_name"]
