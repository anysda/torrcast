"""Tests for receiver-profile selection from passport fields."""

from torrcast.domain.for_passport import for_passport
from torrcast.domain.profile import ANDROID_TV, CAUTIOUS


def test_android_copy_allowlist_matches_the_proven_cmaf_path() -> None:
    assert ANDROID_TV.plays_copy("hevc", 8)
    assert ANDROID_TV.plays_copy("hevc", 10)
    assert ANDROID_TV.plays_copy("vp9", 8)
    assert not ANDROID_TV.plays_copy("h264", 10), "Hi10P остаётся в перекоде"
    assert not ANDROID_TV.plays_copy("av1", 8)
    assert not CAUTIOUS.plays_copy("hevc", 8), "осторожный профиль не меняется"


def test_known_receiver_can_be_named_in_any_passport_field() -> None:
    assert for_passport(maker="Xiaomi") is ANDROID_TV
    assert for_passport(name="Android TV") is ANDROID_TV
    assert for_passport(model="unknown") is CAUTIOUS
