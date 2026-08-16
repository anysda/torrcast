"""Зеркало :mod:`torrcast.domain.sorted`."""

from torrcast.domain.sorted import _sorted


def test_sorted_is_exposed() -> None:
    assert _sorted is not None
