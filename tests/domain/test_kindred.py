"""Зеркало :mod:`torrcast.domain.kindred`."""

from torrcast.domain.kindred import _kindred


def test_kindred_is_exposed() -> None:
    assert _kindred is not None
