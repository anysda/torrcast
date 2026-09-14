"""Подзаголовок - слово, а не кусок слова: :func:`_by_subtitle` на коротких именах."""

from torrcast.domain.by_subtitle import _by_subtitle
from torrcast.domain.picture import Picture


def test_a_short_query_inside_another_word_is_not_a_subtitle() -> None:
    """🔴 «Мы» находило «Посланник Тьмы» и «Мини-фильмы»: слог, а не подзаголовок."""
    pictures = [
        Picture(title="Хроники: Посланник Тьмы", year=2008),
        Picture(title="Мультики: Мини-фильмы", year=2012),
        Picture(title="Остров: Край мыса", year=2010),
    ]

    assert _by_subtitle("Мы", pictures) == []


def test_a_short_query_standing_as_a_word_of_the_subtitle_is_found() -> None:
    pictures = [Picture(title="Говорящий Том Герои: Мы - супер!", year=2019)]

    assert [p.title for p in _by_subtitle("Мы", pictures)] == [pictures[0].title]


def test_the_leading_words_of_a_long_subtitle_still_find_it() -> None:
    """Начало подзаголовка словами - вход прежний: «Kaede to Suzu» без хвоста."""
    pictures = [Picture(title="Каэдэ", year=2023, original="Hibike: Kaede to Suzu The Animation")]

    assert [p.title for p in _by_subtitle("Kaede to Suzu", pictures)] == ["Каэдэ"]
