"""Зеркало :mod:`torrcast.domain.in_digits`."""

from torrcast.domain.in_digits import in_digits


def test_in_digits_is_exposed() -> None:
    assert in_digits is not None
