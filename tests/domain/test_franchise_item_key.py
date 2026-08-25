"""Зеркало :mod:`torrcast.domain.franchise_item_key`: порядок частей внутри франшизы."""

from torrcast.domain.franchise_item_key import _franchise_item_key
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _picture(title: str, year: int | None, part: int | None = None, copies: int = 0) -> Picture:
    return Picture(
        title=title,
        year=year,
        part=part,
        releases=[Release(raw_name=title, title=title) for _ in range(copies)],
    )


def test_the_older_part_goes_first() -> None:
    """Франшиза читается по годам: смотреть её начинают с начала."""
    parts = [_picture("Брат 2", 2000), _picture("Брат", 1997)]

    assert [p.title for p in sorted(parts, key=_franchise_item_key)] == ["Брат", "Брат 2"]


def test_a_picture_without_a_year_waits_at_the_end() -> None:
    """Год неизвестен - место в ряду тоже: такую ставим последней, а не первой."""
    parts = [_picture("Без года", None), _picture("Брат 2", 2000)]

    assert [p.title for p in sorted(parts, key=_franchise_item_key)] == ["Брат 2", "Без года"]


def test_one_year_is_broken_by_the_named_part_and_then_by_weight() -> None:
    """Внутри года порядок решает номер части, а при равном - число раздач."""
    parts = [
        _picture("Вторая", 2000, part=2),
        _picture("Первая", 2000, part=1),
        _picture("Редкая", 2000, copies=1),
        _picture("Частая", 2000, copies=9),
    ]

    assert [p.title for p in sorted(parts, key=_franchise_item_key)] == [
        "Первая",
        "Вторая",
        "Частая",
        "Редкая",
    ]
