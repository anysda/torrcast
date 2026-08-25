"""Зеркало :mod:`torrcast.domain.link`: какие тёзки признаются одной франшизой."""

from torrcast.domain.link import _link
from torrcast.domain.picture import Picture


def _joined(pictures: list[Picture], same: list[int]) -> list[tuple[int, int]]:
    seen: list[tuple[int, int]] = []
    _link(pictures, same, lambda left, right: seen.append((left, right)))
    return seen


def test_years_that_stand_next_to_each_other_make_one_chain() -> None:
    """Тёзки соседних лет - это части одной франшизы, а не разные картины."""
    pictures = [Picture(title="Брат", year=1997), Picture(title="Брат", year=1998)]

    assert _joined(pictures, [0, 1]) == [(0, 1)]


def test_a_gap_of_years_leaves_the_namesakes_apart() -> None:
    """Между 1997 и 2010 - другое кино с тем же названием, и склеивать их нельзя."""
    pictures = [Picture(title="Брат", year=1997), Picture(title="Брат", year=2010)]

    assert _joined(pictures, [0, 1]) == []


def test_a_picture_without_a_year_joins_the_only_chain_there_is() -> None:
    """Год не назван - примыкает к единственной цепочке: другой ей всё равно нет."""
    pictures = [Picture(title="Брат", year=1997), Picture(title="Брат", year=None)]

    assert _joined(pictures, [0, 1]) == [(0, 1)]


def test_a_picture_without_a_year_stays_out_when_there_is_more_than_one_chain() -> None:
    """Цепочек две - к какой примыкать, неизвестно, и догадка тут запрещена."""
    pictures = [
        Picture(title="Брат", year=1997),
        Picture(title="Брат", year=2010),
        Picture(title="Брат", year=None),
    ]

    assert _joined(pictures, [0, 1, 2]) == []
