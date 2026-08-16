"""Зеркало :mod:`torrcast.domain.both_words`."""

from torrcast.domain.both_words import _both_words


def test_both_words_is_exposed() -> None:
    assert _both_words is not None
