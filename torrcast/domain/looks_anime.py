"""Правило looks anime; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain._name_data.data_3 import _ANIME_RE


def looks_anime(text: str) -> bool:
    return bool(_ANIME_RE.search(text))


__all__ = ["looks_anime"]
