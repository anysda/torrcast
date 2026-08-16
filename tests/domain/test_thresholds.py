"""Tests for the effective receiver-threshold snapshot."""

from torrcast.domain.profile import ANDROID_TV
from torrcast.domain.thresholds import thresholds
from torrcast.state import Config


def test_snapshot_names_profile_and_explicit_configuration() -> None:
    raw = Config(hls_segment=8.0)
    values, sources = thresholds(raw, raw, ANDROID_TV, frozenset({"hls_segment"}))
    assert values["patience"] == 577.0
    assert sources["patience"] == "профиль androidtv"
    assert sources["hls_segment"] == "написан в конфиге"
