"""Зеркало :mod:`torrcast.domain.free_first`."""

from torrcast.domain.free_first import _free_first


def test_free_first_is_exposed() -> None:
    assert _free_first is not None
