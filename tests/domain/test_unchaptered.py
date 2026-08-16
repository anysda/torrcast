"""Зеркало :mod:`torrcast.domain.unchaptered`."""

from torrcast.domain.unchaptered import _unchaptered


def test_unchaptered_is_exposed() -> None:
    assert _unchaptered is not None
