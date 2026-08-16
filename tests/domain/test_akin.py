"""Зеркало :mod:`torrcast.domain.akin`."""

from torrcast.domain.akin import _akin


def test_akin_is_exposed() -> None:
    assert _akin is not None
