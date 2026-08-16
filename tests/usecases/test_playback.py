"""Зеркально проверяет сценарий сопровождения показа."""

from torrcast.usecases.playback import _play


def test_playback_scenario_is_importable() -> None:
    assert _play is not None
