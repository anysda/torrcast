"""Зеркало :mod:`torrcast.domain.both_languages`: одна картина, набранная двумя именами."""

from torrcast.domain.both_languages import both_languages
from torrcast.domain.picture import Picture


def _picture(title: str, year: int | None) -> Picture:
    return Picture(title=title, year=year)


def test_the_twin_group_joins_the_asked_one() -> None:
    """Одну картину трекеры зовут по-русски и латиницей: обе горсти - один список."""
    groups = {"брат": [_picture("Брат", 1997)], "brother": [_picture("Brother", 1997)]}

    found = both_languages(groups, {"brother": "брат"}, "брат")

    assert [p.title for p in found] == ["Brother", "Брат"]


def test_a_group_of_another_time_and_kind_stays_apart() -> None:
    """Тёзка через двадцать лет - другая картина, и в список запроса ей нельзя."""
    groups = {
        "брат": [Picture(title="Брат", year=1997, kind="movie")],
        "brother": [Picture(title="Brother", year=2019, kind="tv")],
    }

    found = both_languages(groups, {"brother": "брат"}, "брат")

    assert [p.title for p in found] == ["Брат"]


def test_a_group_without_a_twin_is_left_as_it_is() -> None:
    groups = {"брат": [_picture("Брат", 1997), _picture("Брат 2", 2000)]}

    assert [p.title for p in both_languages(groups, {}, "брат")] == ["Брат", "Брат 2"]
