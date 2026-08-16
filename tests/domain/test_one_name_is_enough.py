"""Зеркало :mod:`torrcast.domain.one_name_is_enough`."""

from torrcast.domain.one_name_is_enough import _one_name_is_enough


def test_one_name_is_enough_is_exposed() -> None:
    assert _one_name_is_enough is not None
