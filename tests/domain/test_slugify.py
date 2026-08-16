"""Зеркало :mod:`torrcast.domain.slugify`."""

from torrcast.domain.slugify import slugify


def test_slugify_is_exposed() -> None:
    assert slugify is not None
