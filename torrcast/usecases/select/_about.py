"""Строка показа по записи состояния: картина, серия, качество, дорожка и место."""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.usecases.rank._hms import _hms


def _about(entry: Entry) -> str:
    """Строка показа по записи состояния: «Киберпанк» · s1e2 · дорожка 1 · с 0:03:20.

    Студия называется отдельным словом, если подпись дорожки о ней молчит: у сезонной
    раздачи подпись это голое ``rus``, и по ней человек не отличит студию, которой он
    смотрит сериал, от любой другой (:attr:`torrcast.domain.entry.Entry.studio`).
    """
    voice = entry.voice or f"дорожка {entry.audio + 1}"
    if entry.studio and entry.studio.casefold() not in voice.casefold():
        voice = f"{voice} ({entry.studio})"
    parts = [f"«{entry.title}»", entry.label, entry.quality, voice]
    if entry.pos > 0:
        parts.append(f"с {_hms(entry.pos)}")
    return " · ".join(filter(None, parts))
