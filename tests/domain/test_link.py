"""Зеркало :mod:`torrcast.domain.link`."""

from torrcast.domain.link import _link


def test_link_is_exposed() -> None:
    assert _link is not None
