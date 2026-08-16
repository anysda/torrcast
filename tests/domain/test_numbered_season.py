"""Зеркало :mod:`torrcast.domain.numbered_season`."""

from torrcast.domain.numbered_season import _numbered_season


def test_numbered_season_is_exposed() -> None:
    assert _numbered_season is not None
