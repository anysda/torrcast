"""Зеркало :mod:`torrcast.domain.find_year`."""

from torrcast.domain.find_year import _find_year


def test_find_year_is_exposed() -> None:
    assert _find_year is not None
