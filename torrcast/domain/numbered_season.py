"""Правило numbered season; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.picture import Picture
from torrcast.domain.seasons_named import seasons_named


def _numbered_season(picture: Picture) -> bool:
    return (
        picture.kind == "tv"
        and picture.part is not None
        and (seasons_named(picture) == (picture.part,))
    )


__all__ = ["_numbered_season"]
