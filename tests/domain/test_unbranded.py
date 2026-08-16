"""Зеркало :mod:`torrcast.domain.unbranded`."""

from torrcast.domain.unbranded import _unbranded


def test_unbranded_is_exposed() -> None:
    assert _unbranded is not None
