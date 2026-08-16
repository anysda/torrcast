"""Зеркало :mod:`torrcast.domain.anime_indexer`."""

from torrcast.domain.anime_indexer import anime_indexer


def test_anime_indexer_is_exposed() -> None:
    assert anime_indexer is not None
