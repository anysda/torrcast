"""Сколько мегабайт перекодированного лежит в каталоге впрок.

Спрашивает его нитка кодировщика (:func:`torrcast.adapters.recode.work._work`)."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from torrcast.domain.segment_container import MPEGTS, SegmentContainer
from torrcast.domain.segment_suffix import segment_suffix

if TYPE_CHECKING:
    from pathlib import Path


def spare_weight(spare: Path, container: SegmentContainer = MPEGTS) -> float:
    """Вес готовых кусков в каталоге, МБ; пропавший под руками кусок не считается.

    По этому числу кодировщик и засыпает под потолком кэша: куски лежат в tmpfs, то
    есть в оперативной памяти, и расти им бесконечно нельзя.
    """
    total = 0
    for path in spare.glob(f"v*{segment_suffix(container)}"):
        with contextlib.suppress(OSError):
            total += path.stat().st_size
    return total / 1e6
