"""Whether a map picture is the one a query means by the year it names."""

from __future__ import annotations

from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.own_release import YEAR_SLACK


def map_in_year(picture: MapPicture, year: int) -> bool:
    """The picture's own year is the named one, give or take :data:`YEAR_SLACK`.

    A series is dated by its first year here too, as the menu prints it. Taking any later
    year for a series let «Звери 2026», a 2026 picture the map does not know yet, be
    recognized as the 2016 series «Звери.»: the series then led the circle and the
    picture's own round was never asked. A year that names no picture of the map leaves
    the query unrecognized, and the circle searches it as typed.

    Both recognizers ask this one rule, the web's prefix index
    (:func:`hass.catalog_picture.catalog_picture`) and the command line's exact name
    (:func:`torrcast.domain.facts.map_recognize.map_recognize`): two copies of it would
    drift apart silently.
    """
    return picture.year is not None and abs(picture.year - year) <= YEAR_SLACK


__all__ = ["map_in_year"]
