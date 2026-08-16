"""Проверки порядка озвучек."""

from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.voice_order import voice_order


def test_russian_dub_precedes_original() -> None:
    assert voice_order(AudioTrack(1, "rus", "Дубляж")) < voice_order(
        AudioTrack(0, "eng", "Original")
    )
