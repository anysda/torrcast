"""Правило seasons named; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.picture import Picture


def seasons_named(picture: Picture) -> tuple[int, ...]:
    named = {s for r in picture.releases for s in r.seasons or ((r.season,) if r.season else ())}
    return tuple(sorted(named))


__all__ = ["seasons_named"]
