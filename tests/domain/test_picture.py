"""Зеркало :mod:`torrcast.domain.picture`."""

from torrcast.domain.picture import Picture


def test_picture_is_exposed() -> None:
    assert Picture is not None
