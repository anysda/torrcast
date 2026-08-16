"""Зеркало :mod:`torrcast.domain.looks_anime`."""

from torrcast.domain.looks_anime import looks_anime


def test_looks_anime_is_exposed() -> None:
    assert looks_anime is not None
