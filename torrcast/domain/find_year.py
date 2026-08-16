"""Правило find year; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain._name_data import _YEAR_PATTERNS


def _find_year(text: str) -> tuple[int | None, tuple[int, int] | None]:
    for pattern in _YEAR_PATTERNS:
        match = pattern.search(text)
        if match:
            return (int(match.group(1)), match.span())
    return (None, None)


__all__ = ["_find_year"]
