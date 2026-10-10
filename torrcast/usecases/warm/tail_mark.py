"""Где кончается прогретый последний кусок фильма: и у куска TS, и у фрагмента CMAF.

Спрашивает сверка прогретого куска перед показом
(:func:`torrcast.usecases.feed_pack.feed_segment._warm`) о последнем куске фильма.
"""

from __future__ import annotations

import math
import struct
from typing import TYPE_CHECKING, Final

from torrcast.domain.tape_scales import tape_scales
from torrcast.usecases.warm.segment_end import segment_end
from torrcast.usecases.warm.settings import TS_SYNC

if TYPE_CHECKING:
    from pathlib import Path

#: Заголовок бокса: четыре байта размера и четыре - имени.
_BOX_HEAD: Final = 8
#: Сколько боксов проходим на одном уровне, прежде чем счесть файл мусором.
_MAX_BOXES: Final = 256
#: Флаги ``tfhd``: смещение данных, номер описания, длительность сэмпла по умолчанию.
_BASE_OFFSET, _DESCRIPTION, _TFHD_DURATION = 0x1, 0x2, 0x8
#: Флаги ``trun``: смещение данных, флаги первого сэмпла и поля каждого сэмпла.
_DATA_OFFSET, _FIRST_FLAGS = 0x1, 0x4
_SAMPLE_FIELDS: Final = (0x100, 0x200, 0x400, 0x800)


def tail_mark(path: Path, head: Path, began: float) -> float:
    """Метка конца куска на ленте показа; ``nan`` - честное «не прочли».

    Кусок TS несёт метки фильма сам (:func:`segment_end`). Фрагмент CMAF их не несёт вовсе:
    его счётчик ``tfdt`` считает прогон муксера, а не фильм
    (:func:`torrcast.usecases.warm.segment_start.segment_start`). Зато длину свою он несёт
    честно - сэмплы в ``trun`` с длительностями, - и конец куска тут - его начало на сетке
    ``began`` плюс длина самой длинной дорожки, ровно как у TS конец меряется по любой.

    🔴 До этой правки мера хвоста читала только TS и на ``.m4s`` молчала: обрезанный
    прогретый хвост уходил приставке как здоровый, и сетка, вставшая по концу картинки,
    обещала кусок, которого в файле нет. Заголовок прогрева ``head`` нужен ради шкал дорожек
    и длительностей по умолчанию (``trex``): голый фрагмент их не несёт.
    """
    try:
        with path.open("rb") as handle:
            first = handle.read(1)
    except OSError:
        return math.nan
    if first == bytes((TS_SYNC,)):
        return segment_end(path)
    span = _span(path, head)
    return began + span


def _span(path: Path, head: Path) -> float:
    """Длина самой длинной дорожки фрагмента в секундах; ``nan`` - не прочли."""
    try:
        init = head.read_bytes()
        piece = path.read_bytes()
    except OSError:
        return math.nan
    scales = tape_scales(init)
    defaults = {
        _u32(init, at + 4): _u32(init, at + 12)
        for at, _end in _boxes(init, 0, len(init), b"trex", (b"moov", b"mvex"))
    }
    ticks: dict[int, int] = {}
    for at, end in _boxes(piece, 0, len(piece), b"traf", (b"moof",)):
        track, duration = _traf(piece, at, end, defaults)
        if track:
            ticks[track] = ticks.get(track, 0) + duration
    seconds = [ticks[track] / scales[track] for track in ticks if scales.get(track)]
    return max(seconds) if seconds else math.nan


def _traf(piece: bytes, at: int, end: int, defaults: dict[int, int]) -> tuple[int, int]:
    """Дорожка одного ``traf`` и сумма длительностей его сэмплов в тиках дорожки."""
    tfhd = _boxes(piece, at, end, b"tfhd", ())
    if not tfhd:
        return 0, 0
    place = tfhd[0][0]
    flags = _u32(piece, place) & 0xFFFFFF
    track = _u32(piece, place + 4)
    field = place + 8 + (8 if flags & _BASE_OFFSET else 0) + (4 if flags & _DESCRIPTION else 0)
    default = _u32(piece, field) if flags & _TFHD_DURATION else defaults.get(track, 0)
    total = 0
    for run, run_end in _boxes(piece, at, end, b"trun", ()):
        total += _trun(piece, run, run_end, default)
    return track, total


def _trun(piece: bytes, at: int, end: int, default: int) -> int:
    """Сумма длительностей сэмплов одного ``trun``: своя у сэмпла или по умолчанию."""
    flags = _u32(piece, at) & 0xFFFFFF
    count = _u32(piece, at + 4)
    first = at + 8 + (4 if flags & _DATA_OFFSET else 0) + (4 if flags & _FIRST_FLAGS else 0)
    width = 4 * sum(1 for bit in _SAMPLE_FIELDS if flags & bit)
    if not flags & _SAMPLE_FIELDS[0]:
        return count * default
    if first + count * width > end:
        return 0
    return sum(_u32(piece, first + n * width) for n in range(count))


def _boxes(
    data: bytes, at: int, end: int, want: bytes, into: tuple[bytes, ...]
) -> list[tuple[int, int]]:
    """Нутро каждого бокса ``want`` на этом уровне и внутри боксов ``into``."""
    found: list[tuple[int, int]] = []
    seen = 0
    while at + _BOX_HEAD <= end and seen < _MAX_BOXES:
        seen += 1
        size = _u32(data, at)
        kind = data[at + 4 : at + _BOX_HEAD]
        if size < _BOX_HEAD or at + size > end:
            break
        if kind == want:
            found.append((at + _BOX_HEAD, at + size))
        elif kind in into:
            found += _boxes(data, at + _BOX_HEAD, at + size, want, into)
        at += size
    return found


def _u32(data: bytes, at: int) -> int:
    return int(struct.unpack_from(">I", data, at)[0]) if at + 4 <= len(data) else 0
