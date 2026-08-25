"""Зеркало :mod:`torrcast.domain.both_words`: слова обоих названий картины разом."""

from torrcast.domain.both_words import _both_words
from torrcast.domain.picture import Picture


def test_the_words_of_both_names_are_one_pool() -> None:
    """Запрос смешивает языки, поэтому слова названия и оригинала лежат вместе."""
    picture = Picture(title="Брат 2", year=2000, original="Brother 2")

    assert _both_words(picture) == {"брат", "brother"}


def test_a_picture_without_an_original_name_gives_only_its_own_words() -> None:
    """Отсутствующий оригинал - не пустое слово в наборе, а его отсутствие."""
    assert _both_words(Picture(title="Брат", year=1997)) == {"брат"}
