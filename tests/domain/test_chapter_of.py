"""Зеркало :mod:`torrcast.domain.chapter_of`."""

from torrcast.domain.chapter_of import _chapter_of


def test_chapter_of_is_exposed() -> None:
    assert _chapter_of is not None
