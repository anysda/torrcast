"""Зеркало :mod:`torrcast.domain.word_list`: слова слага, которыми стоит искать."""

from torrcast.domain.word_list import _word_list


def test_the_slug_falls_apart_into_its_words_in_order() -> None:
    assert _word_list("the-matrix-reloaded") == ["the", "matrix", "reloaded"]


def test_a_single_letter_is_not_a_word() -> None:
    """Одиночная буква в имени - это инициал или номер, искать по ней нечего."""
    assert _word_list("brat-2-x") == ["brat"]


def test_a_slug_of_nothing_gives_no_words() -> None:
    assert _word_list("") == []
