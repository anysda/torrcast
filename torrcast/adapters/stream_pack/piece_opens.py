"""Войдёт ли декодер вкладки в кусок с полки; спрашивает начало показа с прогретой головой."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from torrcast.adapters.stream_pack.opens_clean import (
    ENTRY_PACKETS,
    _decodes_quietly,
    _first_slice_idr,
)
from torrcast.domain.hls_wait import ENTRY_TIMEOUT

#: Типы NAL AVC: 1 и 5 - срезы картинки, 7 - SPS, с которого декодер вообще может начать.
_SLICES, _SPS = (1, 5), 7


def piece_opens(
    piece: Path,
    timeout: float = ENTRY_TIMEOUT,
    *,
    run: Callable[..., Any] = subprocess.run,
    clock: Callable[[], float] = time.monotonic,
) -> bool | None:
    """Откроет ли вкладка кусок ``piece`` первым: ``True``/``False``, ``None`` - не сверили.

    🔴 Та же беда, что у входа копией с закладки
    (:func:`torrcast.adapters.stream_pack.opens_clean.opens_clean`), но с полки: прогрев
    режет копию BD-AVC по сетке, и кусок головы начинается I-срезом без IDR, а P-кадры за
    ним несут MMCO на картинки прошлого куска. Живой замер на «Интерстелларе» с закладки
    5348.469: голова v534 с полки, ``PIPELINE_ERROR_DECODE`` и экран «Поток потерян» в
    четырёх продолжениях из четырёх, ни одного кадра.

    Кусок уже лежит на диске, поэтому сверка локальная: его поток ``-f h264`` режется от
    первого SPS (раньше него декодер не начнёт, и вкладка тоже) на :data:`ENTRY_PACKETS`
    картинок, и дальше решают те же две ступени: IDR - сразу ``True``, иначе молчание
    декодера. Нет SPS, не AVC, не прочиталось, декодер не успел - ``None``.
    """
    began = clock()
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(piece),
        "-map", "0:v:0", "-c", "copy", "-f", "h264", "pipe:1",
    ]  # fmt: skip
    try:
        done = run(command, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    entry = _entry(done.stdout)
    first = _first_slice_idr(entry)
    if first is not False:
        return first
    return _decodes_quietly(entry, timeout - (clock() - began), run)


def _entry(stream: bytes) -> bytes:
    """Поток Annex B от первого SPS на :data:`ENTRY_PACKETS` картинок; ``b""`` - SPS нет.

    Хвост режется по началу следующей картинки, вместе с её AUD и SEI: одинокий
    разделитель в конце декодер считает картинкой без среза и жалуется на ровном месте.
    Новая картинка - срез с ``first_mb_in_slice`` 0, то есть старший бит его первого байта.
    """
    start = tail = -1
    pictures = 0
    at = stream.find(b"\x00\x00\x01")
    while at >= 0 and at + 4 < len(stream):
        kind = stream[at + 3] & 0x1F
        if start < 0:
            start = at if kind == _SPS else -1
        elif kind in _SLICES:
            if stream[at + 4] & 0x80:
                pictures += 1
                if pictures > ENTRY_PACKETS:
                    return stream[start : at if tail < 0 else tail]
            tail = -1
        elif tail < 0:
            tail = at
        at = stream.find(b"\x00\x00\x01", at + 3)
    return b"" if start < 0 else stream[start:]
