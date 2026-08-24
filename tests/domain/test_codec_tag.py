"""Tests for CMAF codec tags."""

from torrcast.domain.codec_tag import codec_tag


def test_proven_copy_codecs_have_rfc_6381_tags() -> None:
    assert codec_tag("hevc", 8) == "hvc1.1.6.L120.B0"
    assert codec_tag("hevc", 10) == "hvc1.2.4.L120.B0"
    assert codec_tag("vp9", 8) == "vp09.00.41.08"
