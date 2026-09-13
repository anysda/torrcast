"""Saved-home related shelf priming."""

from __future__ import annotations

from collections.abc import Callable

from web.prime import prime
from web.related_lookup import RelatedLookup


def test_prime_starts_every_saved_tile_without_waiting() -> None:
    """Startup does not leave the tail of the home screen cold."""
    spawned: list[Callable[[], None]] = []
    lookup = RelatedLookup(franchise=lambda *_a: [], spawn=spawned.append)

    prime(lookup, [("Вверх", 2009, "movie"), ("Лука", 2021, "movie")])

    assert len(spawned) == 2
