"""Сколько тиков в секунде у каждой дорожки заголовка.

Спрашивает их склейка, когда встаёт на ленту показа
(:func:`torrcast.adapters.stream_pack.splice_on_tape.splice_on_tape`).
"""

from __future__ import annotations

import struct
from typing import Final

#: Заголовок бокса: четыре байта размера и четыре - имени.
_BOX_HEAD: Final = 8
#: Сколько боксов проходим на одном уровне, прежде чем счесть заголовок мусором.
_MAX_BOXES: Final = 64


def tape_scales(head: bytes) -> dict[int, int]:
    """Сколько тиков в секунде у каждой дорожки заголовка: номер дорожки -> шкала.

    🔴 Без этого счётчик одного куска нельзя переносить в другой. Замер: показ пишет
    картинку шкалой 16000 тиков в секунду, а склейку тот же ffmpeg собирает шкалой 12288 -
    то же число тиков означает в них РАЗНОЕ время, и счётчик, переставленный как есть,
    уводит картинку на 0.768 её места. Звук у обоих 48000, поэтому на слух это не ловится
    вовсе: уезжает одна картинка.
    """
    out: dict[int, int] = {}
    for at, end in _boxes(head, 0, len(head), b"trak", (b"moov",)):
        track = _number(head, _boxes(head, at, end, b"tkhd", ()))
        scale = _number(head, _boxes(head, at, end, b"mdhd", (b"mdia",)))
        if track and scale:
            out[track] = scale
    return out


def _boxes(
    head: bytes, at: int, end: int, want: bytes, into: tuple[bytes, ...]
) -> list[tuple[int, int]]:
    """Нутро каждого бокса ``want``, найденного на этом уровне и внутри боксов ``into``."""
    found: list[tuple[int, int]] = []
    seen = 0
    while at + _BOX_HEAD <= end and seen < _MAX_BOXES:
        seen += 1
        size = struct.unpack(">I", head[at : at + 4])[0]
        kind = head[at + 4 : at + _BOX_HEAD]
        if size < _BOX_HEAD or at + size > end:
            break
        if kind == want:
            found.append((at + _BOX_HEAD, at + size))
        elif kind in into:
            found += _boxes(head, at + _BOX_HEAD, at + size, want, into)
        at += size
    return found


def _number(head: bytes, places: list[tuple[int, int]]) -> int:
    """Число дорожки или её шкалы: оба лежат за парой времён, ширина которых - версия.

    ``tkhd`` и ``mdhd`` устроены одинаково: версия, флаги, создание, правка, а дальше
    искомое поле. Времена у версии 1 по восемь байт, у версии 0 - по четыре, поэтому
    смещение поля считается по версии, а не берётся постоянной.
    """
    for at, end in places:
        version = head[at]
        spot = at + 4 + (16 if version == 1 else 8)
        if spot + 4 <= end:
            return int(struct.unpack(">I", head[spot : spot + 4])[0])
    return 0
