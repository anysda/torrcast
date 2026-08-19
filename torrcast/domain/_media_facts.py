"""Поля паспорта медиафайла: ровно то, что ffprobe вычитал из потока.

Наследует их :class:`torrcast.domain.media.Media`, и только он.
"""

from dataclasses import dataclass

from torrcast.domain.audio_track import AudioTrack


@dataclass(frozen=True, slots=True)
class _MediaFacts:
    """Что ffprobe вычитал из потока: длительность, звуковые дорожки и кодек видео."""

    duration: float = 0.0
    tracks: tuple[AudioTrack, ...] = ()
    video: str | None = None
    height: int = 0
    width: int = 0
    video_bps: float = 0.0
    profile: str | None = None
    pix_fmt: str | None = None
    color_trc: str | None = None
    field_order: str | None = None
