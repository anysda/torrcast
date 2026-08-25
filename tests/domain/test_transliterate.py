"""Зеркало :mod:`torrcast.domain.transliterate`: буква в букву из кириллицы в латиницу."""

from torrcast.domain.transliterate import transliterate


def test_a_russian_name_is_written_letter_by_letter() -> None:
    assert transliterate("Брат") == "brat"


def test_the_digits_and_spacing_survive_the_change() -> None:
    """Второй заход поиска уходит этой строкой, и номер части в ней обязан остаться."""
    assert transliterate("Брат  2") == "brat 2"


def test_a_latin_name_stays_itself_and_only_loses_its_case() -> None:
    assert transliterate("Brother") == "brother"
