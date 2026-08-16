"""Зеркало :mod:`torrcast.domain.split_titles`."""

from torrcast.domain.split_titles import _split_titles


def test_split_titles_is_exposed() -> None:
    assert _split_titles is not None
