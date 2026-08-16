"""Зеркало :mod:`torrcast.domain.catalog_has_name`."""

from torrcast.domain.catalog_has_name import catalog_has_name


def test_catalog_has_name_is_exposed() -> None:
    assert catalog_has_name is not None
