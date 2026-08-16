"""Tests for receiver-profile selection from passport fields."""

from torrcast.domain.for_passport import for_passport
from torrcast.domain.profile import ANDROID_TV, CAUTIOUS


def test_known_receiver_can_be_named_in_any_passport_field() -> None:
    assert for_passport(maker="Xiaomi") is ANDROID_TV
    assert for_passport(name="Android TV") is ANDROID_TV
    assert for_passport(model="unknown") is CAUTIOUS
