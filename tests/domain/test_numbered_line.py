"""Зеркало :mod:`torrcast.domain.numbered_line`: линейка франшизы и всё, что вне её."""

from torrcast.domain.numbered_line import _numbered_line
from torrcast.domain.picture import Picture


def test_the_numbered_parts_make_the_line_and_the_rest_waits_behind() -> None:
    """Номер в меню значит номер части, поэтому линейка и хвост считаются отдельно."""
    line, tail = _numbered_line(
        [
            Picture(title="Брат 2", year=2000, part=2),
            Picture(title="Брат", year=1997),
            Picture(title="Другое кино", year=2010, kind="other"),
        ]
    )

    assert [p.title for p in line] == ["Брат", "Брат 2"]
    assert [p.title for p in tail] == ["Другое кино"]


def test_a_line_without_a_single_number_is_the_whole_pool() -> None:
    """Нумерации нет - значит, и линейки нет: под номерами идёт всё, что нашлось."""
    line, tail = _numbered_line(
        [Picture(title="Брат", year=1997), Picture(title="Сестра", year=2019)]
    )

    assert [p.title for p in line] == ["Брат", "Сестра"]
    assert tail == []


def test_the_parts_of_the_line_stand_in_the_order_of_their_numbers() -> None:
    line, _tail = _numbered_line(
        [Picture(title="Третья", year=2010, part=3), Picture(title="Вторая", year=2000, part=2)]
    )

    assert [p.title for p in line] == ["Вторая", "Третья"]
