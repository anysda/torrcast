"""Зеркало :mod:`torrcast.domain.parse_voices`."""

from torrcast.domain.parse_voices import _parse_voices


def test_parse_voices_is_exposed() -> None:
    assert _parse_voices is not None
