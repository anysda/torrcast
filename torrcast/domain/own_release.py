"""Does a release belong to a picture the map already knows: whole names and the year.

The rule follows JacRed and Radarr in spirit: the picture is known first, and a release
joins it only when one of its whole cleaned names equals one of the picture's names. A
name that merely starts with the picture's name is another work: «Люди Икс: Начало» is
not «Начало», «Оно 2» is not «Оно», «Naruto: Shippuuden» is not «Naruto».
"""

from __future__ import annotations

from typing import Final

from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.name_key import name_key
from torrcast.domain.release import Release

#: How far a movie release's year may stray: festival and premiere years differ by one.
YEAR_SLACK: Final = 1


def _names(known: MapPicture) -> frozenset[str]:
    """The keys a release may be called to belong to the picture."""
    return frozenset(key for key in (name_key(known.name), name_key(known.original)) if key)


def own_release(release: Release, known: MapPicture) -> bool:
    """One of the release names is the picture's, no name is a longer work, the year fits."""
    names = _names(known)
    named = (release.title, release.original, *release.aliases)
    said = {key for name in named if (key := name_key(name))}
    matched = said & names
    if not matched:
        return False
    if any(key.startswith(f"{own}-") for key in said - names for own in names):
        return False
    return _year_fits(release.year, known, len(matched))


def _year_fits(year: int | None, known: MapPicture, matched: int) -> bool:
    if known.year is None:
        return True
    if known.series:
        # A season is dated by its own year: any year from the series start on.
        return year is None or year >= known.year - YEAR_SLACK
    if year is None:
        # Without a year only both names together tell the picture from a namesake.
        return matched >= 2
    return abs(year - known.year) <= YEAR_SLACK


__all__ = ["YEAR_SLACK", "own_release"]
