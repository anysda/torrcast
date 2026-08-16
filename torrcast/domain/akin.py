"""Правило akin; используют модели и фасады разбора имён."""

from __future__ import annotations


def _akin(wanted: str, slug: str) -> bool:
    return bool(wanted) and bool(slug) and (wanted in slug or slug in wanted)


__all__ = ["_akin"]
