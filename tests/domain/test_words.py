"""Зеркало :mod:`torrcast.domain.words`."""

from torrcast.domain.words import _words


def test_words_is_exposed() -> None:
    assert _words is not None
