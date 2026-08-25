"""Зеркало :mod:`torrcast.domain.numbered`: какую картину человек назвал номером."""

from torrcast.domain.numbered import _numbered
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _picture(title: str, year: int, part: int | None = None, copies: int = 1) -> Picture:
    return Picture(
        title=title,
        year=year,
        part=part,
        releases=[Release(raw_name=title, title=title) for _ in range(copies)],
    )


PARTS = [_picture("Брат", 1997), _picture("Брат 2", 2000, part=2)]


def test_the_number_names_the_part_that_carries_it() -> None:
    """«Брат 2» - это вторая часть, а не второй пункт списка."""
    assert [p.title for p in _numbered(PARTS, 2)] == ["Брат 2"]


def test_a_part_without_a_number_of_its_own_is_counted_by_its_place() -> None:
    assert [p.title for p in _numbered(PARTS, 1)] == ["Брат"]


def test_a_number_beyond_the_franchise_names_nothing() -> None:
    """Пятой части нет - это честный отказ, а не последняя из имеющихся."""
    assert _numbered(PARTS, 5) == []


def test_without_a_number_the_whole_franchise_stays() -> None:
    assert [p.title for p in _numbered(PARTS, None)] == ["Брат", "Брат 2"]
