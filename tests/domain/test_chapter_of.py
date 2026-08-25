"""Зеркало :mod:`torrcast.domain.chapter_of`: название, кончающееся словом «часть N»."""

from torrcast.domain.chapter_of import _chapter_of


def test_a_named_chapter_gives_the_franchise_and_the_number() -> None:
    """«Часть 2» - не название, а номер: имя картины остаётся тем же, что у первой."""
    assert _chapter_of("Гарри Поттер: Часть 2") == ("гарри-поттер", 2)


def test_a_roman_number_is_the_same_number() -> None:
    assert _chapter_of("Гарри Поттер: Часть IV") == ("гарри-поттер", 4)


def test_a_bare_number_without_the_word_is_not_a_chapter() -> None:
    """Без слова «часть» число - это просто продолжение, и склеивать их нельзя."""
    assert _chapter_of("Гарри Поттер 2") is None


def test_a_title_without_a_number_at_all_is_not_a_chapter() -> None:
    assert _chapter_of("Гарри Поттер") is None
