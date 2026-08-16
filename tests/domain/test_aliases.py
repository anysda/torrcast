"""Зеркало :mod:`torrcast.domain.aliases`."""

from torrcast.domain.aliases import _aliases


def test_aliases_is_exposed() -> None:
    assert _aliases is not None
