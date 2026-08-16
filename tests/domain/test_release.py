"""Зеркало :mod:`torrcast.domain.release`."""

from torrcast.domain.release import Release


def test_release_is_exposed() -> None:
    assert Release is not None
