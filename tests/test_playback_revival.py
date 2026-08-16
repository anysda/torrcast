"""Проверяет совместимый фасад оживления."""

import torrcast.playback_revival


def test_playback_revival_facade_is_importable() -> None:
    assert torrcast.playback_revival._Revival is not None
