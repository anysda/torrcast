"""Зеркало :mod:`torrcast.domain.franchise_key`."""

from torrcast.domain.franchise_key import franchise_key


def test_franchise_key_is_exposed() -> None:
    assert franchise_key is not None
