"""Как назвать язык дорожки вслух; зовут строки отбора и строка про звук."""

from __future__ import annotations

from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.rank.spoken_key import spoken_key


def spoken(track: AudioTrack) -> str:
    """Как назвать язык дорожки вслух: «японский»; неизвестный — «оригинальный»."""
    return phrase(spoken_key(track))
