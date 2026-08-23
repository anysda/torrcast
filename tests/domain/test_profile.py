"""Tests for the receiver profile model."""

from torrcast.domain.profile import ANDROID_TV, CAUTIOUS, COPY, RECODE, REFUSE


def test_profile_keeps_receiver_measurements_and_codec_rule() -> None:
    assert ANDROID_TV.patience == 577.0
    assert CAUTIOUS.verdict("h264", 8, 1080) == COPY
    assert CAUTIOUS.verdict("h264", 10) == RECODE
    assert CAUTIOUS.verdict("vp9") == REFUSE


def test_only_the_measured_receiver_carries_a_length_ceiling() -> None:
    """Потолок длины куска - замер приставки; у осторожного профиля его нет вовсе.

    🔴 Ноль тут не «забыли поставить», а «окно запроса Q70D не мерено»: число, снятое на
    приставке, чужой профиль не двигает.
    """
    assert ANDROID_TV.max_segment_seconds == 15.0
    assert CAUTIOUS.max_segment_seconds == 0.0
