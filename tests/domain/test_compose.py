"""Зеркало :mod:`torrcast.domain.compose`."""

from torrcast.domain.compose import _compose


def test_compose_is_exposed() -> None:
    assert _compose is not None
