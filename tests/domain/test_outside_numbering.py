"""Зеркало :mod:`torrcast.domain.outside_numbering`: что в меню стоит вне линейки."""

from torrcast.domain.outside_numbering import outside_numbering
from torrcast.domain.picture import Picture


def test_what_does_not_belong_to_the_line_is_named_by_its_key() -> None:
    """Номер меню принадлежит линейке франшизы; всё прочее под ним не значится."""
    aside = Picture(title="Другое кино", year=2010, kind="other")
    pictures = [Picture(title="Брат 2", year=2000, part=2), Picture(title="Брат", year=1997), aside]

    assert outside_numbering(pictures) == {aside.key}


def test_a_pool_that_is_all_line_leaves_nothing_outside() -> None:
    assert outside_numbering([Picture(title="Брат", year=1997)]) == set()
