"""Зеркало :mod:`torrcast.domain.glued_year`."""

from torrcast.domain.glued_year import _glued_year


def test_glued_year_is_exposed() -> None:
    assert _glued_year is not None
