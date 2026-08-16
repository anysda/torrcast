"""Зеркало :mod:`torrcast.domain.same_word`."""

from torrcast.domain.same_word import same_word


def test_same_word_is_exposed() -> None:
    assert same_word is not None
