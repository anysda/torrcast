"""Зеркало :mod:`torrcast.domain.group_weight`."""

from torrcast.domain.group_weight import _group_weight


def test_group_weight_is_exposed() -> None:
    assert _group_weight is not None
