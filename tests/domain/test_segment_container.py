"""Tests for the closed set of HLS segment containers."""

from torrcast.domain.segment_container import FMP4, MPEGTS


def test_container_names_match_ffmpeg_and_load_vocabulary() -> None:
    assert (MPEGTS, FMP4) == ("mpegts", "fmp4")
