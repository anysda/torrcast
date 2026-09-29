"""Перекод места перед склейкой: опорный кадр в начале и сдвиг лент - одним заходом."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from torrcast.ports.journal.slot import journal

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from torrcast.adapters.stream_pack.packer_state import _State


def vet_recode(
    state: _State,
    slot: int,
    copy: Path,
    recode: Path,
    keyless: Callable[[Path], bool],
    shift_of: Callable[[Path, Path], float | None],
) -> None:
    """Снести перекод без опорного кадра в начале; первый годный ещё и меряет сдвиг лент.

    Обе пробы - ffprobe по одним и тем же кускам, и стоят они запуском процесса, а не
    счётом: подряд они стояли на пути первого кадра, разом стоят как одна.
    Сдвиг от перекода без опорного кадра прогону не достаётся: такой кусок сносится.
    """
    with ThreadPoolExecutor(1) as pool:
        shift = pool.submit(shift_of, copy, recode) if state.recode_shift is None else None
        if keyless(recode):
            journal().mark("перекод без опорного кадра", слот=slot)
            recode.unlink(missing_ok=True)
        elif shift is not None:
            state.recode_shift = shift.result() or 0.0
