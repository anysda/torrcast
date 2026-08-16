"""Tests for the explained receiver-profile choice."""

from torrcast.domain.choice import Choice
from torrcast.domain.profile import CAUTIOUS


def test_choice_keeps_profile_and_reason() -> None:
    assert Choice(CAUTIOUS, "default").how == "default"
