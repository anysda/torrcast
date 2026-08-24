"""Tests for receiver-specific HLS segment suffixes."""

from torrcast.domain.segment_container import FMP4, MPEGTS
from torrcast.domain.segment_suffix import segment_suffix


def test_each_container_has_its_own_segment_suffix() -> None:
    assert segment_suffix(MPEGTS) == ".ts"
    assert segment_suffix(FMP4) == ".m4s"
