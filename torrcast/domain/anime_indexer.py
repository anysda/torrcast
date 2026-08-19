"""Правило anime indexer; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain._name_data.data_3 import _ANIME_INDEXERS


def anime_indexer(name: str) -> bool:
    low = name.lower()
    return any(mark in low for mark in _ANIME_INDEXERS)


__all__ = ["anime_indexer"]
