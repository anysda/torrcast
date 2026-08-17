"""Ставит флажок «картинка на экране»; зовёт показ, увидевший PLAYING."""

from __future__ import annotations

import contextlib
from pathlib import Path

from torrcast.adapters.stream_pack.playing_flag import playing_flag


def mark_playing(out: Path) -> None:
    """Показ увидел ``PLAYING``: с этой секунды на экране есть изображение."""
    with contextlib.suppress(OSError):
        playing_flag(out).touch()
