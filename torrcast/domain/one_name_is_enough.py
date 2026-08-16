"""Правило one name is enough; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify
from torrcast.domain.words import _words


def _one_name_is_enough(asked: set[str], picture: Picture) -> bool:
    return any(asked <= _words(slugify(name)) for name in (picture.title, picture.original or ""))


__all__ = ["_one_name_is_enough"]
