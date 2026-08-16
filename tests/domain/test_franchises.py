"""Зеркало :mod:`torrcast.domain.franchises`."""

from torrcast.domain.franchises import franchises


def test_franchises_is_exposed() -> None:
    assert franchises is not None
