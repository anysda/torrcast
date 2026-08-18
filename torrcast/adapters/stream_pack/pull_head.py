"""Греет начало файла - заголовок контейнера, без которого ffmpeg не откроет вход."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from torrcast.adapters.stream_pack.warm_at import warm_at
from torrcast.domain.warm_open import HEAD_WARM


def pull_head(
    source_url: str,
    upto: int = HEAD_WARM,
    alive: Any = None,
    *,
    warm: Callable[[str, int, int, Any], int] = warm_at,
) -> int:
    """Прогреть начало файла — частный случай :func:`warm_at` со смещением ноль.

    ``warm`` - чем греть. Параметром, а не именем модуля: сам прогрев ходит Range-запросами
    в рой, а здесь меряется ровно одно - что смещение ноль, а размер и признак жизни
    доехали как есть.
    """
    return warm(source_url, 0, upto, alive)
