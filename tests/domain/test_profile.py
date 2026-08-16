"""Tests for the receiver profile model."""

from torrcast.domain.profile import ANDROID_TV, CAUTIOUS, COPY, RECODE, REFUSE


def test_profile_keeps_receiver_measurements_and_codec_rule() -> None:
    assert ANDROID_TV.patience == 577.0
    assert CAUTIOUS.verdict("h264", 8, 1080) == COPY
    assert CAUTIOUS.verdict("h264", 10) == RECODE
    assert CAUTIOUS.verdict("vp9") == REFUSE
