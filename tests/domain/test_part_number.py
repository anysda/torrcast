"""Зеркало :mod:`torrcast.domain.part_number`."""

from torrcast.domain.part_number import part_number


def test_part_number_is_exposed() -> None:
    assert part_number is not None
