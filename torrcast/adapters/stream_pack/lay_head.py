"""Кладёт наружу общий заголовок показа; зовёт выкладка упаковщика."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from torrcast.adapters.stream_pack.segment_head import segment_head


def lay_head(piece: Path, out: Path) -> None:
    """Положить наружу общий заголовок показа, если его там ещё нет.

    Манифест называет его ``EXT-X-MAP``, и приёмник берёт его ПЕРВЫМ, до всякого куска:
    без него разбор не начинается вовсе - живой замер на приставке, конвейер стоит в
    ``kStarting``, а куски он при этом качает.

    Годится заголовок ЛЮБОГО куска, и поэтому берётся первый попавшийся: кусок fMP4 у нас
    самодостаточен, свои параметры несёт сам и дальше переопределяет ими то, что приёмник
    прочитал отсюда. Разойтись эти два заголовка могут (копия и перекод описаны
    по-разному), и это не беда, а причина: ровно затем куски и сделаны самодостаточными.
    """
    init = out / "init.mp4"
    if init.exists():
        return
    head = segment_head(piece)
    if not head:
        return
    with contextlib.suppress(OSError):
        # Через временное имя: приёмник читает этот файл один раз и на старте показа,
        # и полузаписанный заголовок стоил бы ему всего показа.
        laying = out / "init.mp4.part"
        laying.write_bytes(head)
        os.replace(laying, init)
