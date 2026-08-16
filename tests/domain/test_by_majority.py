"""Зеркало :mod:`torrcast.domain.by_majority`."""

from torrcast.domain.by_majority import by_majority


def test_by_majority_is_exposed() -> None:
    assert by_majority is not None
