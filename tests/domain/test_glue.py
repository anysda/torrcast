"""Зеркало :mod:`torrcast.domain.glue`."""

from torrcast.domain.glue import glue


def test_glue_is_exposed() -> None:
    assert glue is not None
