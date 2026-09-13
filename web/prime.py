"""Start the related shelves of saved home tiles without delaying startup."""

from __future__ import annotations

from torrcast.usecases.facts import FactPicture
from web.related_lookup import RelatedLookup


def prime(related: RelatedLookup, pictures: list[FactPicture]) -> None:
    """Put every saved tile's related shelf into the shared source client."""
    for picture in pictures:
        related.of(picture[0], len(picture) == 3 and picture[2] == "tv")


__all__ = ["prime"]
