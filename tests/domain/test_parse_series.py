"""Зеркало :mod:`torrcast.domain.parse_series`."""

from torrcast.domain.parse_series import _parse_series


def test_parse_series_is_exposed() -> None:
    assert _parse_series is not None
