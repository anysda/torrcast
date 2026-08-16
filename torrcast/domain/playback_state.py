"""Persistent playback state owned by application scenarios."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlaybackState:
    """Last playback position for a release."""

    key: str
    position: float
