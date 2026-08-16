"""Проверяет совместимый фасад показа."""

import torrcast.playback


def test_playback_facade_is_importable() -> None:
    assert torrcast.playback._play is not None
