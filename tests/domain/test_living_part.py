"""Зеркало :mod:`torrcast.domain.living_part`."""

from torrcast.domain.living_part import _living_part


def test_living_part_is_exposed() -> None:
    assert _living_part is not None
