"""Правило picture season span; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.picture import Picture


def _picture_season_span(picture: Picture) -> tuple[int, int] | None:
    numbers = [
        s
        for r in picture.releases
        for s in r.seasons or ([r.season] if r.season is not None else [])
    ]
    return (min(numbers), max(numbers)) if numbers else None


__all__ = ["_picture_season_span"]
