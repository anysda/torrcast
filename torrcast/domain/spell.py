"""Правило spell; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain._name_data import _SPELL_X
from torrcast.domain.transliterate import transliterate


def spell(text: str) -> str:
    return _SPELL_X.sub("ks", transliterate(text))


__all__ = ["spell"]
