"""Which picture a search means, by the offline map alone: the whole name, or one typo.

Mature trackers know the picture before they ask for releases (Radarr, Lampa with JacRed):
the circle then asks indexers by the picture's own names and year
(:func:`torrcast.usecases.discover.named_round.named_round`). A prefix is not a picture:
«Матр» stays the viewer's text.

Only the Russian release name names a picture, as on the command line
(:func:`torrcast.domain.facts.map_recognize.map_recognize`). The original is shared by
pictures the map does not know yet: «Animals» took the 2016 series «Звери.», whose names
then swallowed the releases of the 2026 film «Животные / Animals», and the web played
the film under the series while the command line played «Животные».
"""

from __future__ import annotations

from typing import Final

from hass.catalog_index import CatalogIndex, _one_edit
from torrcast.domain.asked_year import asked_year
from torrcast.domain.facts.map_in_year import map_in_year
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.facts.map_pictures import map_pictures
from torrcast.domain.name_key import name_key

#: How much better known a typo's picture must be than another near name to be taken.
TYPO_LEAD: Final = 10


def catalog_picture(index: CatalogIndex, query: str, wait: float = 0.0) -> MapPicture | None:
    """The picture the query names; ``wait`` - how long a cold index may still be built."""
    if not index.ready(wait):
        return None
    votes = index.votes()
    whole = _named(index, query, name_key(query), votes)
    if whole:
        return whole[0]
    name, year = asked_year(query)
    wanted = name_key(name)
    exact = _named(index, query, wanted, votes)
    typo = not exact and not any(ch.isdigit() for ch in wanted)
    found = exact or (_near(index, query, wanted, votes) if typo else [])
    if year is not None:
        found = [p for p in found if map_in_year(p, year)]
    if not found:
        return None
    if typo and len({name_key(p.name) for p in found}) > 1:
        runner = next(p for p in found if name_key(p.name) != name_key(found[0].name))
        if found[0].votes < TYPO_LEAD * runner.votes:
            return None
    return found[0]


def _named(index: CatalogIndex, query: str, key: str, votes: dict[str, int]) -> list[MapPicture]:
    rows = [row for row in index.look(query) if key == name_key(row[4])]
    return sorted(map_pictures(rows, votes), key=lambda p: -p.votes)


def _near(index: CatalogIndex, query: str, key: str, votes: dict[str, int]) -> list[MapPicture]:
    rows = [row for row in index.look(query) if _one_edit(key, name_key(row[4]))]
    return sorted(map_pictures(rows, votes), key=lambda p: -p.votes)


__all__ = ["TYPO_LEAD", "catalog_picture"]
