"""Зеркало :mod:`torrcast.domain.normalize`."""

from torrcast.domain.normalize import _normalize


def test_normalize_is_exposed() -> None:
    assert _normalize is not None
