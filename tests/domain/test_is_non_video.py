"""Зеркало :mod:`torrcast.domain.is_non_video`."""

from torrcast.domain.is_non_video import _is_non_video


def test_is_non_video_is_exposed() -> None:
    assert _is_non_video is not None
