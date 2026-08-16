"""Зеркало :mod:`torrcast.domain.by_both_names`."""

from torrcast.domain.by_both_names import _by_both_names


def test_by_both_names_is_exposed() -> None:
    assert _by_both_names is not None
