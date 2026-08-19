"""Правило transliterate; используют модели и фасады разбора имён."""

from __future__ import annotations

import re
import unicodedata

from torrcast.domain._name_data.data_3 import _TRANSLIT


def transliterate(text: str) -> str:
    lowered = unicodedata.normalize("NFKC", text).casefold()
    return re.sub("\\s+", " ", "".join(_TRANSLIT.get(ch, ch) for ch in lowered)).strip()


__all__ = ["transliterate"]
