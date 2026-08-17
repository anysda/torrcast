"""Слот сетки по имени файла сегмента; ``-1`` - имя не наше.

Зовут его раздача сегментов наружу и уборка готовых кусков позади показа."""

from __future__ import annotations

from torrcast.domain.hls_settings import _SEGMENT_RE


def segment_slot(name: str) -> int:
    """Слот по имени файла; ``-1`` — имя не наше."""
    found = _SEGMENT_RE.fullmatch(name)
    return int(found.group(1)) if found else -1
