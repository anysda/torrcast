"""Which picture of the offline map a search names: its whole text, or its name and year.

The command line has no prefix index of the map (the web builds one on start, see
:func:`hass.catalog_picture.catalog_picture`), but the exact name is enough to ask the
indexers by the picture's own names: «Дюна» is then asked as «Dune 2021» too, and the
releases titled only in Latin stop missing from the pool.
"""

from __future__ import annotations

from torrcast.domain.asked_year import asked_year
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.facts.proof_in_map import KnownPictures
from torrcast.domain.own_release import YEAR_SLACK


def map_recognize(known: KnownPictures, query: str) -> MapPicture | None:
    """The best-known map picture under the query's exact name, of its year when one is named."""
    if whole := known(query):
        return max(whole, key=lambda picture: picture.votes)
    name, year = asked_year(query)
    if year is None or name == query:
        return None
    found = [picture for picture in known(name) if _in_year(picture, year)]
    return max(found, key=lambda picture: picture.votes, default=None)


def _in_year(picture: MapPicture, year: int) -> bool:
    if picture.year is None:
        return False
    if picture.series:
        return picture.year <= year + YEAR_SLACK
    return abs(picture.year - year) <= YEAR_SLACK


__all__ = ["map_recognize"]
