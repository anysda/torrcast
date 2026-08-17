"""Греет начало файла - заголовок контейнера, без которого ffmpeg не откроет вход."""

from __future__ import annotations

from typing import Any

from torrcast.adapters.stream_pack.warm_at import warm_at
from torrcast.domain.warm_open import HEAD_WARM


def pull_head(source_url: str, upto: int = HEAD_WARM, alive: Any = None) -> int:
    """Прогреть начало файла — частный случай :func:`warm_at` со смещением ноль."""
    return warm_at(source_url, 0, upto, alive)
