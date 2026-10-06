"""Whether a picture is a numbered part of the franchise a query names."""

from __future__ import annotations

from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.picture import Picture


def part_of_franchise(picture: Picture, key: str) -> bool:
    """A numbered part whose title or original's root is the franchise ``key``.

    A numbered part of another franchise («Агашки по вызову 2: Начало») says nothing
    about the asked name: the guards of the first part and of the full name stand only
    over the parts of the franchise the query named.
    """
    if picture.part is None:
        return False
    if picture.original and franchise_key(picture.original) == key:
        return True
    return picture.franchise == key


__all__ = ["part_of_franchise"]
