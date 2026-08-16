"""Зеркало :mod:`torrcast.domain.reads_season`."""

from torrcast.domain.reads_season import reads_season


def test_reads_season_is_exposed() -> None:
    assert reads_season is not None
