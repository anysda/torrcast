"""Правило run span; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.picture import Picture


def _run_span(picture: Picture) -> tuple[int, int] | None:
    numbers = [
        n
        for r in picture.releases
        if r.episodes and (not r.seasons) and (r.season is None)
        for n in (r.episodes[0], r.episodes[-1])
    ]
    return (min(numbers), max(numbers)) if numbers else None


__all__ = ["_run_span"]
