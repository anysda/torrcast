"""Зеркало :mod:`torrcast.domain.transliterate`."""

from torrcast.domain.transliterate import transliterate


def test_transliterate_is_exposed() -> None:
    assert transliterate is not None
