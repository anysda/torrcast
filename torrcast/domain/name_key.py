"""A name as a comparison key: the slug without diacritics."""

from __future__ import annotations

import unicodedata

from torrcast.domain.slugify import slugify


def name_key(name: str | None) -> str:
    """Slug of the name with combining marks dropped: «Shippûden» is «Shippuden»."""
    if not name:
        return ""
    plain = unicodedata.normalize("NFKD", name)
    return slugify("".join(char for char in plain if not unicodedata.combining(char)))


__all__ = ["name_key"]
