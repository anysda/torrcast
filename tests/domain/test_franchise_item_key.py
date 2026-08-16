"""Зеркало :mod:`torrcast.domain.franchise_item_key`."""

from torrcast.domain.franchise_item_key import _franchise_item_key


def test_franchise_item_key_is_exposed() -> None:
    assert _franchise_item_key is not None
