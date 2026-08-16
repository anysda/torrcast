"""Зеркало :mod:`torrcast.domain.by_alias`."""

from torrcast.domain.by_alias import _by_alias


def test_by_alias_is_exposed() -> None:
    assert _by_alias is not None
