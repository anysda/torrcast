"""Tests for the persistent playback-state value."""

from torrcast.domain.playback_state import PlaybackState


def test_keeps_release_position() -> None:
    assert PlaybackState("movie", 12.5).position == 12.5
