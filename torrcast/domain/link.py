"""Правило link; используют модели и фасады разбора имён."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain.continued import _continued
from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify


def _link(pictures: list[Picture], same: list[int], union: Callable[[int, int], None]) -> None:
    dated = sorted(
        (i for i in same if pictures[i].year is not None),
        key=lambda i: (pictures[i].year or 0, pictures[i].title, pictures[i].original or ""),
    )
    chains: list[list[int]] = []
    for i in dated:
        current = pictures[i]
        year = current.year or 0
        previous = pictures[chains[-1][-1]] if chains else None
        close_outlier = False
        if previous is not None and previous.original and current.original:
            close_outlier = (
                year - (previous.year or 0) == 2
                and len(previous.releases) == 1
                and (len(current.releases) >= 10)
                and (slugify(previous.original) == slugify(current.original))
            )
        if previous is not None and (year - (previous.year or 0) <= 1 or close_outlier):
            chains[-1].append(i)
        else:
            chains.append([i])
    for chain in chains:
        for i in chain[1:]:
            union(chain[0], i)
    chains = _continued(pictures, chains, union)
    blank = [i for i in same if pictures[i].year is None]
    if len(chains) > 1:
        return
    for i in blank[1:]:
        union(blank[0], i)
    if chains and blank:
        union(chains[0][0], blank[0])


__all__ = ["_link"]
