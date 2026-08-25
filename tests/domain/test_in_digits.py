"""Зеркало :mod:`torrcast.domain.in_digits`: числительное словом становится цифрой."""

from torrcast.domain.in_digits import in_digits


def test_a_number_written_as_a_word_becomes_a_digit() -> None:
    """«Один дома два» и «Один дома 2» - один запрос: у трекеров он пишется обоими."""
    assert in_digits("один-дома-два") == "1-дома-2"


def test_an_english_numeral_counts_the_same() -> None:
    assert in_digits("home-alone-two") == "home-alone-2"


def test_the_words_that_are_not_numbers_are_left_alone() -> None:
    assert in_digits("матрица-перезагрузка") == "матрица-перезагрузка"
