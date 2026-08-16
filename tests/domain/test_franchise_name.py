"""Зеркало :mod:`torrcast.domain.franchise_name`."""

from torrcast.domain.franchise_name import franchise_name


def test_franchise_name_is_exposed() -> None:
    assert franchise_name is not None
