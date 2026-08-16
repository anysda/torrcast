"""Зеркало :mod:`torrcast.domain.parse_source`."""

from torrcast.domain.parse_source import _parse_source


def test_parse_source_is_exposed() -> None:
    assert _parse_source is not None
