"""Правило season span; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain._named_seasons import _named_seasons


def _season_span(text: str) -> tuple[int, ...]:
    return _named_seasons(text)


__all__ = ["_season_span"]
