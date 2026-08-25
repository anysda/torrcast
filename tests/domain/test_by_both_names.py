"""Зеркало :mod:`torrcast.domain.by_both_names`: запрос, где смешаны оба языка картины."""

from torrcast.domain.by_both_names import _by_both_names
from torrcast.domain.picture import Picture


def test_a_query_that_mixes_the_two_names_finds_the_picture() -> None:
    """«Брат Brother» не найдётся ни одним названием - только обоими сразу."""
    pictures = [Picture(title="Брат", year=1997, original="Brother")]

    assert [p.title for p in _by_both_names("Брат Brother", pictures)] == ["Брат"]


def test_a_query_that_one_name_answers_by_itself_is_not_this_case() -> None:
    """Одного названия хватило - значит, искать смесью нечего, и путь не тот."""
    pictures = [Picture(title="Брат по крови", year=1997, original="Brother")]

    assert _by_both_names("Брат по крови", pictures) == []


def test_a_single_word_query_is_not_a_mix_of_names() -> None:
    assert _by_both_names("Брат", [Picture(title="Брат", year=1997, original="Brother")]) == []
