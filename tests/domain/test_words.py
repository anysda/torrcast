"""Зеркало :mod:`torrcast.domain.words`: слова имени как набор, без порядка и повторов."""

from torrcast.domain.words import _words


def test_the_words_come_back_as_a_set() -> None:
    """Сравниваются имена вложением наборов, поэтому порядок слов тут значения не имеет."""
    assert _words("the-matrix-reloaded") == {"the", "matrix", "reloaded"}


def test_a_word_repeated_twice_is_one_word() -> None:
    assert _words("brat-brat") == {"brat"}
