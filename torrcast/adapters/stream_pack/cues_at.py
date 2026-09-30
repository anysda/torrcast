"""Где у mkv индекс (``Cues``): прогрев продолжения с середины греет его за заголовком."""

from __future__ import annotations

from typing import Any, Final

from torrcast.adapters.frames.http_range_reader import HttpRangeReader
from torrcast.adapters.frames.keyframes import HEAD_PEEK, Source
from torrcast.domain.frames.mkv.head import Head

#: Шаг чтения головы: между шагами прогрев спрашивает ``alive``, как ``warm_at`` на мегабайт.
STEP: Final = 64 << 10


def cues_at(source_url: str, alive: Any = None, *, source: Source = HttpRangeReader) -> int | None:
    """Смещение ``Cues`` из головы файла; показ начался (``alive`` ложно) - ``None``."""
    reader = source(source_url)
    head = b""
    while len(head) < HEAD_PEEK:
        if alive is not None and not alive():
            return None
        part = reader.read(len(head), min(STEP, HEAD_PEEK - len(head)))
        if not part:
            break
        head += part
    return Head(head).cues_at
