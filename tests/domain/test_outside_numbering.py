"""Зеркало :mod:`torrcast.domain.outside_numbering`."""

from torrcast.domain.outside_numbering import outside_numbering


def test_outside_numbering_is_exposed() -> None:
    assert outside_numbering is not None
