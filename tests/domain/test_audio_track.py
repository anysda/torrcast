"""Проверки модели звуковой дорожки."""

from torrcast.domain.audio_track import AudioTrack


def test_label_omits_unknown_language() -> None:
    assert AudioTrack(0, "und", "Дубляж / AC3 / 6 ch").label == "Дубляж"
