"""Зеркало :mod:`torrcast.domain.paired`."""

from torrcast.domain.paired import _paired


def test_paired_is_exposed() -> None:
    assert _paired is not None
