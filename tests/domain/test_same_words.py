"""Зеркало :mod:`torrcast.domain.same_words`."""

from torrcast.domain.same_words import same_words


def test_same_words_is_exposed() -> None:
    assert same_words is not None
