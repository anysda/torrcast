"""Зеркало :mod:`torrcast.domain.aliases`: чьё оригинальное имя ведёт на какую группу."""

from torrcast.domain.aliases import _aliases
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _picture(title: str, original: str | None, copies: int) -> Picture:
    releases = [Release(raw_name=title, title=title) for _ in range(copies)]
    return Picture(title=title, year=1997, original=original, releases=releases)


def test_the_original_name_points_at_the_group_that_carries_it() -> None:
    """Латинское имя картины - вход в её же группу, набранную по русскому названию."""
    groups = {"брат": [_picture("Брат", "Brother", 1)]}

    assert _aliases(groups) == {"brother": "брат"}


def test_the_heavier_group_wins_the_shared_name() -> None:
    """Одно имя у двух групп - ведёт оно к той, где раздач больше: там и картина живее."""
    groups = {
        "тонкий": [_picture("Тонкий", "Brother", 1)],
        "толстый": [_picture("Толстый", "Brother", 5)],
    }

    assert _aliases(groups) == {"brother": "толстый"}


def test_a_picture_without_an_original_name_leads_nowhere() -> None:
    groups = {"брат": [_picture("Брат", None, 3)]}

    assert _aliases(groups) == {}
