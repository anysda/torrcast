"""Зеркало :mod:`torrcast.domain.same_words`: два слага из одних и тех же слов."""

from torrcast.domain.same_words import same_words


def test_the_same_words_in_another_order_are_the_same_name() -> None:
    assert same_words("матрица-перезагрузка", "перезагрузка-матрица")


def test_a_name_with_a_word_of_its_own_is_another_name() -> None:
    assert not same_words("матрица-перезагрузка", "матрица-революция")
