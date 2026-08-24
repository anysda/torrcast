"""Tests for the single-variant CMAF master playlist."""

from torrcast.domain.master_manifest import master_manifest


def test_master_names_video_and_aac_codecs() -> None:
    text = master_manifest("hvc1.2.4.L120.B0")

    assert 'CODECS="hvc1.2.4.L120.B0,mp4a.40.2"' in text
    assert text.splitlines()[-1] == "stream.m3u8"
