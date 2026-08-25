"""Зеркало :mod:`torrcast.domain.free_first`: безномерная первая часть у нумерованных."""

from torrcast.domain.free_first import _free_first
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _picture(title: str, year: int | None, original: str | None = None, copies: int = 1) -> Picture:
    return Picture(
        title=title,
        year=year,
        original=original,
        releases=[Release(raw_name=title, title=title) for _ in range(copies)],
    )


NUMBERED = [Picture(title="Брат 2", year=2000, original="Brother 2", part=2)]


def test_the_picture_named_by_the_franchise_itself_is_the_first_part() -> None:
    """У первой части номера нет: её имя и есть имя франшизы."""
    found = _free_first([_picture("Брат", 1997)], NUMBERED)

    assert found is not None
    assert found.title == "Брат"


def test_a_stranger_is_not_taken_for_the_first_part() -> None:
    """Ни своим именем, ни латинским корнем к франшизе не привязана - значит, чужая."""
    assert (
        _free_first([_picture("Матрица: Перезагрузка", 2003, "The Matrix: Reloaded")], NUMBERED)
        is None
    )


def test_the_liveliest_of_the_earlier_ones_takes_the_place() -> None:
    """Раньше нумерованных их несколько - берём ту, у которой раздач больше."""
    found = _free_first(
        [_picture("Брат", 1997, copies=1), _picture("Брат", 1995, copies=7)], NUMBERED
    )

    assert found is not None
    assert found.year == 1995


def test_nothing_to_choose_from_is_an_honest_nothing() -> None:
    assert _free_first([], NUMBERED) is None
