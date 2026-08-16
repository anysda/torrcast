"""Зеркало :mod:`torrcast.domain.numbered`."""

from torrcast.domain.numbered import _numbered


def test_numbered_is_exposed() -> None:
    assert _numbered is not None
