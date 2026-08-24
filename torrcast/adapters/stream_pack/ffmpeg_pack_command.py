"""Собирает команду ffmpeg для упаковки по сетке; зовут упаковщик, прогрев и перекод."""

from __future__ import annotations

from typing import Any

from torrcast.adapters.ffmpeg.pack_command import pack_command
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.domain.hls_settings import (
    AUDIO_BITRATE,
    AUDIO_CHANNELS,
    AUDIO_CODEC,
    PACK_LIST,
    SPLIT_SLACK,
)


def ffmpeg_pack_command(
    source_url: str,
    audio_index: int,
    run_dir: str,
    grid: Grid,
    slot: int,
    at: float,
    readrate: float = 1.0,
    burst: float = 0.0,
    encode: Any = None,
    until: int = -1,
    seek: float | None = None,
) -> list[str]:
    """Совместимый фасад сборки команды упаковщика."""
    return pack_command(
        source_url,
        audio_index,
        run_dir,
        grid,
        slot,
        at,
        readrate,
        burst,
        encode,
        until,
        seek=seek,
        split_slack=SPLIT_SLACK,
        audio_codec=AUDIO_CODEC,
        audio_channels=AUDIO_CHANNELS,
        audio_bitrate=AUDIO_BITRATE,
        pack_list=PACK_LIST,
    )
