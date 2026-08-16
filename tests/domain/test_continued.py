"""Зеркало :mod:`torrcast.domain.continued`."""

from torrcast.domain.continued import _continued


def test_continued_is_exposed() -> None:
    assert _continued is not None
