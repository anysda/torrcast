"""Tests for the receiver profile model unit."""

from torrcast.domain.receiver_profile import CAUTIOUS, COPY, RECODE, REFUSE, ReceiverProfile


def test_profile_model_owns_the_codec_verdict() -> None:
    """Модель, вынесенная из фасада, сохраняет своё публичное решение."""
    profile = ReceiverProfile(key="test", title="test", recode_codecs=frozenset({"hevc"}))

    assert profile.verdict("h264") == COPY
    assert profile.verdict("hevc") == RECODE
    assert profile.verdict("av1") == REFUSE


def test_the_cautious_seek_thresholds_stay_where_they_were_measured() -> None:
    """Откатная проба: 15.0 и 60.0 сняты на Q70D, и вынос их в профиль их не двигает.

    Послабление с приставки в осторожное умолчание уехать не должно: этими числами
    живёт телевизор, а сняты они на mpegts и на нём же остаются.
    """
    assert CAUTIOUS.jump == 15.0
    assert CAUTIOUS.seam_lead == 60.0
