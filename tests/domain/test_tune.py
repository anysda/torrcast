"""Tests for applying receiver thresholds to configuration values."""

from dataclasses import dataclass, replace

from torrcast.domain.profile import ANDROID_TV, CAUTIOUS
from torrcast.domain.tune import tune


@dataclass(frozen=True)
class _Config:
    hls_segment: float = 10.0
    hls_burst: float = 60.0
    bitrate_warn_mbit: float = 16.0
    recode_at_mbit: float = 10.0
    recode_mbit: float = 9.0
    hls_jump: float = 15.0
    hls_seam_lead: float = 60.0


def test_profile_changes_defaults_but_not_written_values() -> None:
    assert tune(_Config(), ANDROID_TV).bitrate_warn_mbit == 28.0
    assert tune(_Config(bitrate_warn_mbit=12.0), ANDROID_TV).bitrate_warn_mbit == 12.0


def test_the_seek_thresholds_of_the_receiver_ride_through_the_same_door() -> None:
    """Порог ожидания и задел стыка приходят из профиля, а не из умолчания класса ленты.

    До этой правки оба числа не проходили через :func:`tune` вовсе и доезжали до любого
    приёмника осторожными - снятыми на Q70D и на mpegts.
    """
    own = replace(ANDROID_TV, jump=9.0, seam_lead=41.0)
    tuned = tune(_Config(), own)

    assert (tuned.hls_jump, tuned.hls_seam_lead) == (9.0, 41.0)


def test_a_handwritten_seek_threshold_stays_stronger_than_the_profile() -> None:
    """Написанное руками сильнее профиля - ровно как у соседей по :func:`tune`."""
    own = replace(ANDROID_TV, jump=9.0, seam_lead=41.0)
    tuned = tune(_Config(hls_jump=7.5, hls_seam_lead=33.0), own)

    assert (tuned.hls_jump, tuned.hls_seam_lead) == (7.5, 33.0)


def test_the_cautious_profile_keeps_the_seek_thresholds_it_was_measured_with() -> None:
    """Откатная проба: у осторожного профиля оба числа остаются ровно прежними."""
    tuned = tune(_Config(), CAUTIOUS)

    assert (tuned.hls_jump, tuned.hls_seam_lead) == (15.0, 60.0)
    assert (CAUTIOUS.jump, CAUTIOUS.seam_lead) == (15.0, 60.0)
