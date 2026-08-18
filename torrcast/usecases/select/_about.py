"""Строка показа по записи состояния: картина, серия, качество, дорожка и место."""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.usecases.rank._hms import _hms


def _about(entry: Entry) -> str:
    """Строка показа по записи состояния: «Киберпанк» · s1e2 · дорожка 1 · с 0:03:20."""
    voice = entry.voice or f"дорожка {entry.audio + 1}"
    parts = [f"«{entry.title}»", entry.label, entry.quality, voice]
    if entry.pos > 0:
        parts.append(f"с {_hms(entry.pos)}")
    return " · ".join(filter(None, parts))
