"""Зеркало :mod:`torrcast.domain.word_list`."""

from torrcast.domain.word_list import _word_list


def test_word_list_is_exposed() -> None:
    assert _word_list is not None
