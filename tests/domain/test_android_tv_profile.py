"""Tests for the measured Android TV receiver profile."""

from torrcast.domain.android_tv_profile import ANDROID_TV


def test_android_tv_profile_keeps_its_public_identity() -> None:
    """Разрез модуля не превращает именованный профиль в безымянный набор чисел."""
    assert ANDROID_TV.key == "androidtv"
    assert "Android TV" in ANDROID_TV.title
    assert ANDROID_TV.max_segment_bytes == 28_000_000
