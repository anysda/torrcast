"""Зеркало :mod:`torrcast.domain.by_words`."""

from torrcast.domain.by_words import _by_words


def test_by_words_is_exposed() -> None:
    assert _by_words is not None
