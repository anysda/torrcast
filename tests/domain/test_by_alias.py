"""Зеркало :mod:`torrcast.domain.by_alias`: находим картину по её третьему имени."""

from torrcast.domain.by_alias import _by_alias
from torrcast.domain.picture import Picture


def test_a_picture_is_found_by_a_name_that_is_neither_of_its_two() -> None:
    """Третье имя пишут сами раздачи, и запрос приходит именно им."""
    pictures = [Picture(title="Брат", year=1997, aliases=("кровь-и-бетон",))]

    assert [p.title for p in _by_alias("Кровь и бетон", pictures)] == ["Брат"]


def test_one_name_shared_by_two_franchises_finds_nothing() -> None:
    """Имя, ведущее сразу в две разные картины, не ведёт никуда: это не находка."""
    pictures = [
        Picture(title="Брат", year=1997, aliases=("тезка",)),
        Picture(title="Сестра", year=2019, aliases=("тезка",)),
    ]

    assert _by_alias("Тёзка", pictures) == []


def test_the_whole_franchise_comes_in_the_order_of_its_parts() -> None:
    """Найденная франшиза отдаётся целиком и по годам: первая часть идёт первой."""
    pictures = [
        Picture(title="Брат 2", year=2000, aliases=("тезка",)),
        Picture(title="Брат", year=1997, aliases=("тезка",)),
    ]

    assert [p.title for p in _by_alias("Тёзка", pictures)] == ["Брат", "Брат 2"]


def test_an_empty_query_is_not_a_name() -> None:
    assert _by_alias("  ", [Picture(title="Брат", year=1997, aliases=("",))]) == []
