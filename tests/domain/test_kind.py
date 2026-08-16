"""Зеркало :mod:`torrcast.domain.kind`."""

from torrcast.domain.kind import Kind


def test_kind_is_exposed() -> None:
    assert Kind is not None
