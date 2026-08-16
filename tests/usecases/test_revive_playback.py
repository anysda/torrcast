"""Зеркально проверяет сценарий оживления показа."""

from torrcast.usecases.revive_playback import _Revival


def test_revival_scenario_is_importable() -> None:
    assert _Revival is not None
