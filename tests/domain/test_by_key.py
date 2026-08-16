"""Tests for receiver-profile lookup by key."""

from torrcast.domain.by_key import by_key
from torrcast.domain.profile import ANDROID_TV


def test_key_is_normalized_and_unknown_key_is_rejected() -> None:
    assert by_key(" AndroidTV ") is ANDROID_TV
    assert by_key("missing") is None
