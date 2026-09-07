"""Зеркало :mod:`torrcast.domain.picture_names`: все имена одной картины."""

from __future__ import annotations

from torrcast.domain.picture import Picture
from torrcast.domain.picture_names import picture_names


def test_all_four_kinds_of_name_are_in_the_set() -> None:
    picture = Picture(
        title="Лучшие дни",
        year=2019,
        original="Shao nian de ni",
        also="Better Days",
        aliases=("better-days",),
    )

    assert picture_names(picture) == {"Лучшие дни", "Shao nian de ni", "Better Days", "better-days"}


def test_a_picture_named_once_is_named_once() -> None:
    assert picture_names(Picture(title="Брат", year=1997)) == {"Брат"}


def test_an_empty_name_names_nothing_and_does_not_enter_the_set() -> None:
    """Пустое имя совпало бы со всякой картиной без оригинала - в наборе его нет."""
    assert "" not in picture_names(Picture(title="Брат", year=1997, original=None, also=""))
