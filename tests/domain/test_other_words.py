"""Зеркало :mod:`torrcast.domain.other_words`."""

from torrcast.domain.other_words import other_words


def test_other_words_is_exposed() -> None:
    assert other_words is not None
