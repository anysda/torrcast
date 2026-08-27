"""Счётчики ленты дорожек внутри куска CMAF: где они лежат и что в них стоит.

Спрашивает их склейка, когда встаёт на ленту показа
(:func:`torrcast.adapters.stream_pack.splice_on_tape.splice_on_tape`).
"""

from __future__ import annotations

import struct
from typing import Final, NamedTuple

#: Заголовок бокса: четыре байта размера и четыре - имени.
_BOX_HEAD: Final = 8
#: Сколько боксов проходим внутри одного ``moof``, прежде чем счесть его мусором.
_MAX_BOXES: Final = 64
#: Ширина счётчика: ``tfdt`` версии 0 несёт его в четырёх байтах, версии 1 - в восьми.
_WIDE: Final = 8
_NARROW: Final = 4
#: Потолок узкого счётчика: за ним число уже не влезает, и переписать кусок нечем.
_NARROW_MAX: Final = (1 << 32) - 1


class _Spot(NamedTuple):
    """Один счётчик ленты: где он лежит в куске, какой ширины, чей и что в нём стоит."""

    at: int
    width: int
    track: int
    mark: int


def tape_spots(block: bytes, base: int = 0) -> tuple[_Spot, ...]:
    """Все счётчики ленты внутри одного ``moof``; пусто - счётчиков там нет.

    🔴 На CMAF ``tfdt`` - это НЕ время фильма, а счётчик дорожки: сколько её длительностей
    муксер уже написал за этот прогон. Замер живого показа («Матрица: Революция», прогон с
    1:42:14): у выложенных кусков подряд звук идёт 0, 476160, 954368, 1432576, 1911808,
    2390016 тиков при 48000 тиках в секунде, то есть ровно по длине куска, а картинка того
    же куска стоит на 10 с дальше звука - у каждой дорожки счётчик свой и начинается он там,
    где муксер написал её первый сэмпл.

    Ровно поэтому лента куска не сохраняется НИЧЕМ на входе: ни ``-copyts``,
    ни ``-output_ts_offset``, ни ``-avoid_negative_ts disabled``, ни сегментный муксер
    самого упаковщика (замер: шесть наборов флагов, все шесть дали ноль). Счётчик считает
    прогон, а склейка - это новый прогон ffmpeg, и счёт у него начинается с нуля.

    ``base`` - смещение блока в файле: с ним :attr:`_Spot.at` сразу указывает в файл, и
    переписывающему не приходится складывать смещения самому.

    Считается по дереву ``moof/traf``, а номер дорожки берётся из ``tfhd`` того же ``traf``:
    порядок дорожек внутри куска не обещан никем, и опираться на него значило бы переставить
    звук на ленту картинки на первом же куске, где муксер написал их иначе.
    """
    found: list[_Spot] = []
    _walk(block, 0, len(block), base, 0, found)
    return tuple(found)


def _walk(block: bytes, at: int, end: int, base: int, track: int, found: list[_Spot]) -> None:
    """Пройти боксы отрезка, запоминая, чья это дорожка, и собрать её счётчики."""
    seen = 0
    while at + _BOX_HEAD <= end and seen < _MAX_BOXES:
        seen += 1
        size = struct.unpack(">I", block[at : at + 4])[0]
        kind = block[at + 4 : at + _BOX_HEAD]
        step = _BOX_HEAD
        if size == 1:
            if at + 16 > end:
                return
            size = struct.unpack(">Q", block[at + _BOX_HEAD : at + 16])[0]
            step = 16
        if size < step or at + size > end:
            return
        if kind in (b"moof", b"traf"):
            track = _inside(block, at + step, at + size, base, track, found)
        at += size


def _inside(block: bytes, at: int, end: int, base: int, track: int, found: list[_Spot]) -> int:
    """Разобрать нутро ``moof`` или ``traf``: чья дорожка и какие у неё счётчики."""
    seen = 0
    while at + _BOX_HEAD <= end and seen < _MAX_BOXES:
        seen += 1
        size = struct.unpack(">I", block[at : at + 4])[0]
        kind = block[at + 4 : at + _BOX_HEAD]
        if size < _BOX_HEAD or at + size > end:
            return track
        if kind == b"traf":
            _inside(block, at + _BOX_HEAD, at + size, base, track, found)
        elif kind == b"tfhd" and at + 16 <= end:
            track = struct.unpack(">I", block[at + 12 : at + 16])[0]
        elif kind == b"tfdt" and at + 12 <= end:
            spot = _spot(block, at, base, track)
            if spot is not None:
                found.append(spot)
        at += size
    return track


def _spot(block: bytes, at: int, base: int, track: int) -> _Spot | None:
    """Счётчик из одного ``tfdt``; ``None`` - версия бокса не та, что мы умеем читать."""
    version = block[at + _BOX_HEAD]
    value_at = at + 12
    if version == 1:
        if value_at + _WIDE > len(block):
            return None
        return _Spot(
            base + value_at,
            _WIDE,
            track,
            struct.unpack(">Q", block[value_at : value_at + _WIDE])[0],
        )
    if version == 0:
        if value_at + _NARROW > len(block):
            return None
        return _Spot(
            base + value_at,
            _NARROW,
            track,
            struct.unpack(">I", block[value_at : value_at + _NARROW])[0],
        )
    return None
