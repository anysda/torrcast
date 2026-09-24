"""Происхождение картины как имя единственной дорожки без языка и заголовка."""

from __future__ import annotations

from typing import Final, Literal

from torrcast.domain.audio_track import AudioTrack

type UnnamedTrackOrigin = Literal["", "foreign", "native"]

UNNAMED_TRACK_KEYS: Final[dict[str, str]] = {
    "foreign": "select.track_foreign_unnamed",
    "native": "select.track_native_unnamed",
}


def unnamed_track_origin(track: AudioTrack, *, native: bool, lone: bool) -> UnnamedTrackOrigin:
    """Кем назвать полностью безымянную дорожку, когда она одна во всём файле.

    Тег языка или содержательный заголовок сильнее происхождения картины. Несколько
    безымянных дорожек тоже не получают один и тот же язык: происхождение не различает
    их, поэтому человеку остаются честные номера.
    """
    if not lone or track.named or track.clean_title:
        return ""
    return "native" if native else "foreign"


__all__ = ["UNNAMED_TRACK_KEYS", "UnnamedTrackOrigin", "unnamed_track_origin"]
