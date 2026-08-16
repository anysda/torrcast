"""Description of one media-transcoding operation."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TranscodeJob:
    """Input, output and playback offset for the transcoder."""

    source_url: str
    output_dir: str
    start_at: float = 0.0
    audio_track: int = 0
