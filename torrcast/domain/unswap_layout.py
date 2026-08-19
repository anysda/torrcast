"""Правило unswap layout; используют модели и фасады разбора имён."""

from __future__ import annotations

import unicodedata

from torrcast.domain._name_data.data_3 import _LAYOUT


def unswap_layout(text: str) -> str:
    lowered = unicodedata.normalize("NFKC", text).casefold()
    return "".join(_LAYOUT.get(ch, ch) for ch in lowered)


__all__ = ["unswap_layout"]
