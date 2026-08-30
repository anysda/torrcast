"""Английский каталог кластера ``media_binaries``: он же умолчание, он же запасной."""

from __future__ import annotations


def en() -> dict[str, str]:
    return {
        "media_binaries.ffmpeg_missing": "ffmpeg is not installed",
        "media_binaries.ffprobe_missing": "ffprobe is not installed",
        "media_binaries.ffprobe_timed_out": "ffprobe did not wait for the stream",
        "media_binaries.ffprobe_failed": "ffprobe failed to read the stream: {reason}",
    }
