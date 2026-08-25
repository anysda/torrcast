"""Зеркало :mod:`torrcast.domain.subtitles`: подзаголовки обоих имён картины."""

from torrcast.domain.picture import Picture
from torrcast.domain.subtitles import _subtitles


def test_the_words_after_the_colon_of_both_names_are_taken() -> None:
    """Подзаголовком картину и спрашивают: имя франшизы человек не повторяет."""
    picture = Picture(title="Матрица: Перезагрузка", year=2003, original="The Matrix: Reloaded")

    assert _subtitles(picture) == {"перезагрузка", "reloaded"}


def test_a_name_without_a_colon_has_no_subtitle() -> None:
    assert _subtitles(Picture(title="Брат", year=1997)) == set()
