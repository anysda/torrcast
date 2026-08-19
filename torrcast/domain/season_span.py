"""Правило season span; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain._name_data.data_2 import _SEASON_SPAN_RES


def _season_span(text: str) -> tuple[int, ...]:
    for pattern in _SEASON_SPAN_RES:
        match = pattern.search(text)
        if match:
            first, last = (int(match.group(1)), int(match.group(2)))
            if 0 < first < last <= 40:
                return tuple(range(first, last + 1))
    return ()


__all__ = ["_season_span"]
