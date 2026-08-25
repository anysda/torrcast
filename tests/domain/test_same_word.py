"""Зеркало :mod:`torrcast.domain.same_word`: одно ли это слово в разных формах."""

from torrcast.domain.same_word import same_word


def test_a_word_in_another_case_is_the_same_word() -> None:
    """Запрос и название расходятся падежом, а слово за ними одно."""
    assert same_word("матрица", "матрицы")


def test_a_russian_word_and_its_latin_spelling_are_the_same_word() -> None:
    assert same_word("матрица", "matritsa")


def test_two_different_words_stay_different() -> None:
    assert not same_word("матрица", "молоко")


def test_a_shared_beginning_is_not_enough_by_itself() -> None:
    """«Матрица» и «Математика» начинаются одинаково, но это разные слова."""
    assert not same_word("матрица", "математика")
