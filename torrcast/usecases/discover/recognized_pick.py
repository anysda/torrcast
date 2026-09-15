"""Pictures of a search whose picture the offline map already recognized.

The recognized picture takes exactly the releases that are its own
(:func:`~torrcast.domain.own_release.own_release`), from the rows of the viewer's text and of
the picture's names alike. The other pictures come from the viewer's text only and are
sorted by it as before: a namesake or a sequel never borrows the picture's releases, and a
row the picture's names brought never becomes a tile of its own.
"""

from __future__ import annotations

from dataclasses import replace

import torrcast.usecases.discover._search_state as _search_state
from torrcast.domain.cluster import cluster
from torrcast.domain.compose import _compose
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.own_release import own_release
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.discover.franchise_pick import franchise_pick


def recognized_pick(
    query: str, typed: list[RawResult], named: list[RawResult], known: MapPicture | None
) -> tuple[list[Picture], list[Picture]]:
    """All pictures of the pool, and the found ones: the recognized picture first."""
    catalogue = _search_state._search_catalogue
    releases = catalogue.to_releases(typed)
    pool = catalogue.to_releases(catalogue.merge(typed, named)) if named else releases
    pictures = cluster(pool)
    if known is None:
        return pictures, franchise_pick(query, pictures)
    own = [release for release in pool if own_release(release, known)]
    if not own:
        return pictures, franchise_pick(query, cluster(releases))
    # The map names the picture, not the rows: asking «Up 2009» beside «Вверх» brings
    # releases titled in Latin, and the viewer would read his own picture under a foreign name.
    lead = replace(
        _compose("tv" if known.series else "movie", known.year, own),
        title=known.name,
        original=known.original or None,
    )
    others = cluster([release for release in releases if not own_release(release, known)])
    return pictures, [lead, *(p for p in franchise_pick(query, others) if p.key != lead.key)]


__all__ = ["recognized_pick"]
