"""Правило franchise key; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.franchise_name import franchise_name
from torrcast.domain.slugify import slugify


def franchise_key(title: str) -> str:
    return slugify(franchise_name(title)) or slugify(title)


__all__ = ["franchise_key"]
