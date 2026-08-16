"""Tests for the media-transcoding request value."""

from torrcast.domain.transcode_job import TranscodeJob


def test_keeps_requested_start_position() -> None:
    assert TranscodeJob("source", "/tmp/out", 4).start_at == 4
