"""Tests for applying receiver thresholds to configuration values."""

from dataclasses import dataclass

from torrcast.domain.profile import ANDROID_TV
from torrcast.domain.tune import tune


@dataclass(frozen=True)
class _Config:
    hls_segment: float = 10.0
    hls_burst: float = 60.0
    bitrate_warn_mbit: float = 16.0
    recode_at_mbit: float = 10.0
    recode_mbit: float = 9.0


def test_profile_changes_defaults_but_not_written_values() -> None:
    assert tune(_Config(), ANDROID_TV).bitrate_warn_mbit == 28.0
    assert tune(_Config(bitrate_warn_mbit=12.0), ANDROID_TV).bitrate_warn_mbit == 12.0
