"""Копия, которой нужен собственный GOP из-за левого соседа."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from torrcast.adapters.stream_pack.packer_state import _State


def unsafe_copy(
    state: _State,
    path: Path,
    source: Path,
    slot: int,
    keyless: Callable[[Path], bool],
    after_recode: Callable[[int], bool] | None,
) -> bool:
    """Нужна ли keyless-копии своя картинка вместо стыка с x264 слева."""
    # Ровная сетка режет копию посреди GOP. После перекода или ужатия СЛЕВА такой
    # кусок не декодируется: его PPS остался у исходника, а у соседа уже x264.
    # Две копии подряд образуют один поток и безопасны. На сетке по опорным кадрам
    # проба не нужна и не стоит ни одного ffprobe.
    seam = after_recode if after_recode is not None else state.after_recode
    return (
        state.shrink is not None
        and source is path
        and not state.outward
        and not bool(getattr(state.grid, "on_keys", False))
        and keyless(path)
        and seam is not None
        and seam(slot)
    )
