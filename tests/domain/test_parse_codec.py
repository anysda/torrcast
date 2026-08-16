"""Зеркало :mod:`torrcast.domain.parse_codec`."""

from torrcast.domain.parse_codec import _parse_codec


def test_parse_codec_is_exposed() -> None:
    assert _parse_codec is not None
