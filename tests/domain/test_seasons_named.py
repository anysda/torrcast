"""Зеркало :mod:`torrcast.domain.seasons_named`."""

from torrcast.domain.seasons_named import seasons_named


def test_seasons_named_is_exposed() -> None:
    assert seasons_named is not None
