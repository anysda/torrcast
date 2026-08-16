"""Зеркало :mod:`torrcast.domain.alias_slugs`."""

from torrcast.domain.alias_slugs import _alias_slugs


def test_alias_slugs_is_exposed() -> None:
    assert _alias_slugs is not None
