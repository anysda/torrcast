"""Уборка готовых кусков позади показа: их час прошёл, tmpfs не резиновый.

Зовёт её нитка кодировщика (:func:`torrcast.adapters.recode.work._work`)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.stream_probe.segment_slot import segment_slot

if TYPE_CHECKING:
    from pathlib import Path

    from torrcast.adapters.stream_pack.grid import Grid


def sweep_spare(spare: Path, grid: Grid, played: float, done: set[int]) -> None:
    """Выбросить перекодированные куски позади показа и забыть, что они были готовы.

    Позади показа держится окно в 30 секунд, а не выбрасывается всё: перемотка назад
    бывает короткой, и заново перекодировать только что сыгранное было бы вдвое дороже,
    чем подержать его в памяти.
    """
    behind = grid.slot_at(max(0.0, played - 30.0))
    for path in spare.glob("v*.ts"):
        slot = segment_slot(path.name)
        if 0 <= slot < behind:
            path.unlink(missing_ok=True)
            done.discard(slot)
