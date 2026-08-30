"""Русский каталог кластера ``media_binaries``."""

from __future__ import annotations


def ru() -> dict[str, str]:
    return {
        "media_binaries.ffmpeg_missing": "ffmpeg не установлен",
        "media_binaries.ffprobe_missing": "ffprobe не установлен",
        "media_binaries.ffprobe_timed_out": "ffprobe не дождался потока",
        "media_binaries.ffprobe_failed": "ffprobe не прочитал поток: {reason}",
    }
