"""Умолчания сухого приёмника: они и есть осторожный профиль, а не отдельные числа."""

from __future__ import annotations

from torrcast.adapters.chromecast.mock.mock_settings import _Settings
from torrcast.domain.profile import CAUTIOUS


def test_the_defaults_are_the_cautious_profile_and_nothing_of_their_own() -> None:
    """Замер 09-08-2026 на живом Q70D: числа живут в профиле, а тут только умолчание."""
    assert _Settings.PATIENCE == CAUTIOUS.patience == 23.5
    assert CAUTIOUS.segment_retries == _Settings.SEGMENT_RETRIES
    assert CAUTIOUS.sulk == _Settings.SULK
    assert _Settings.WAKE_TIMEOUT == 60.0, "попытка тут не одна, интервалы держит зовущий"
