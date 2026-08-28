"""Tests for the receiver profile model unit."""

from torrcast.domain.receiver_profile import COPY, RECODE, REFUSE, ReceiverProfile


def test_profile_model_owns_the_codec_verdict() -> None:
    """Модель, вынесенная из фасада, сохраняет своё публичное решение."""
    profile = ReceiverProfile(key="test", title="test", recode_codecs=frozenset({"hevc"}))

    assert profile.verdict("h264") == COPY
    assert profile.verdict("hevc") == RECODE
    assert profile.verdict("av1") == REFUSE
