"""Уборка готовых кусков позади показа: их час прошёл, tmpfs не резиновый.

Зовёт её нитка кодировщика (:func:`torrcast.adapters.recode.work._work`)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.stream_probe.segment_slot import segment_slot
from torrcast.domain.head_name import head_name
from torrcast.domain.hls_settings import HEAD_SENT
from torrcast.domain.segment_container import MPEGTS, SegmentContainer
from torrcast.domain.segment_suffix import segment_suffix

if TYPE_CHECKING:
    from pathlib import Path

    from torrcast.adapters.stream_pack.grid import Grid


def sweep_spare(
    spare: Path,
    grid: Grid,
    played: float,
    done: set[int],
    container: SegmentContainer = MPEGTS,
) -> None:
    """Выбросить перекодированные куски позади показа и забыть, что они были готовы.

    Позади показа держится окно в 30 секунд, а не выбрасывается всё: перемотка назад
    бывает короткой, и заново перекодировать только что сыгранное было бы вдвое дороже,
    чем подержать его в памяти.
    """
    behind = grid.slot_at(max(0.0, played - 30.0))
    for path in spare.glob(f"v*{segment_suffix(container)}"):
        slot = segment_slot(path.name)
        if 0 <= slot < behind:
            path.unlink(missing_ok=True)
            # Заголовок этого места ушёл наружу вместе с куском или не понадобился вовсе,
            # а запись о выложенном заголовке нужна ровно соседу, который давно позади.
            (spare / head_name(slot)).unlink(missing_ok=True)
            (spare / head_name(slot, HEAD_SENT)).unlink(missing_ok=True)
            done.discard(slot)
