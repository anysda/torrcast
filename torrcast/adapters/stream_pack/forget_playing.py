"""Убирает флажок картинки; зовут подготовка каталога и конец показа."""

from __future__ import annotations

import contextlib
from pathlib import Path

from torrcast.adapters.stream_pack.playing_flag import playing_flag


def forget_playing(out: Path) -> None:
    """Убрать флажок: следующий показ обязан доказать картинку заново."""
    with contextlib.suppress(OSError):
        playing_flag(out).unlink(missing_ok=True)
