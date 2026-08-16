"""Зеркало :mod:`torrcast.domain.subtitles`."""

from torrcast.domain.subtitles import _subtitles


def test_subtitles_is_exposed() -> None:
    assert _subtitles is not None
