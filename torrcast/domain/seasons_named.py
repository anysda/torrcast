"""Правило seasons named; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.picture import Picture
from torrcast.domain.seasons_in import seasons_in


def seasons_named(picture: Picture) -> tuple[int, ...]:
    return seasons_in(picture.releases)


__all__ = ["seasons_named"]
