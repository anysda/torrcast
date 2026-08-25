"""Зеркало :mod:`torrcast.domain.sorted`: порядок картин в собранном каталоге."""

from torrcast.domain.picture import Picture
from torrcast.domain.sorted import _sorted


def test_the_older_picture_comes_first() -> None:
    found = _sorted([Picture(title="Брат 2", year=2000), Picture(title="Брат", year=1997)])

    assert [p.title for p in found] == ["Брат", "Брат 2"]


def test_a_picture_without_a_year_waits_at_the_end() -> None:
    found = _sorted([Picture(title="Без года", year=None), Picture(title="Брат 2", year=2000)])

    assert [p.title for p in found] == ["Брат 2", "Без года"]


def test_one_year_is_broken_by_the_title_so_the_order_never_wobbles() -> None:
    """Порядок обязан повторяться от прогона к прогону: номер в меню значит картину."""
    found = _sorted([Picture(title="Яма", year=2000), Picture(title="Дом", year=2000)])

    assert [p.title for p in found] == ["Дом", "Яма"]
