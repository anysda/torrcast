"""Кандидаты карты имён под одним прокатным именем, сведённые с голосами IMDb."""

from __future__ import annotations

from torrcast.domain.facts.imdb_rows import _TV_KINDS, _RuName
from torrcast.domain.facts.map_picture import MapPicture


def map_pictures(candidates: list[_RuName], votes: dict[str, int]) -> list[MapPicture]:
    """Все картины карты под именем: сериал и фильм не смешиваются, голоса по ``tconst``."""
    return [
        MapPicture(
            name=name,
            year=int(year) if year.isdigit() else None,
            series=kind in _TV_KINDS,
            original=original,
            votes=votes.get(tconst, 0),
        )
        for tconst, kind, original, year, name in candidates
    ]


__all__ = ["map_pictures"]
