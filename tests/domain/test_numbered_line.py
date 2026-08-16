"""Зеркало :mod:`torrcast.domain.numbered_line`."""

from torrcast.domain.numbered_line import _numbered_line


def test_numbered_line_is_exposed() -> None:
    assert _numbered_line is not None
