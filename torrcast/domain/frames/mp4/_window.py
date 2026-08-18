"""Окно в ``moov`` и шаг по боксам ISO BMFF: чем разбор mp4 читает файл.

Зовут его все части разбора: и поиск дорожки видео, и таблицы сэмплов.
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator

from torrcast.domain.frames.range_reader import RangeReader as Reader

#: Каким шагом дочитывается ``moov``. Разбор идёт строго вперёд, поэтому куски ложатся
#: подряд - для роя это лучший из возможных запросов. Мельче делать нечего: заход к
#: холодной раздаче стоит дороже мегабайта, крупнее - начинаем тянуть дорожку звука,
#: которая нам не нужна.
MOOV_CHUNK: Final = 1 << 20


class _Window:
    """Кусок файла, который дочитывается по мере надобности — и только вперёд.

    Разбор ``moov`` идёт сверху вниз и никогда не возвращается назад, поэтому окно растёт
    подряд идущими Range-запросами и обрывается там, где разбору перестало быть нужно.
    Ровно поэтому дорожка звука (у «Моаны 2» это 3.2 МБ из 5.3) не читается вовсе: она
    лежит за дорожкой видео.
    """

    def __init__(self, reader: Reader, base: int, size: int, have: bytes = b"") -> None:
        self.reader = reader
        self.base = base
        self.size = size
        self.data = have[:size]

    def need(self, upto: int) -> None:
        """Дочитать так, чтобы байт ``upto`` (от начала окна) был на месте."""
        want = min(upto, self.size)
        if want <= len(self.data):
            return
        want = min(self.size, max(want, len(self.data) + MOOV_CHUNK))
        self.data += self.reader.read(self.base + len(self.data), want - len(self.data))

    def take(self, at: int, size: int) -> bytes:
        self.need(at + size)
        return self.data[at : at + size]


def _boxes(window: _Window, start: int, end: int) -> Iterator[tuple[bytes, int, int]]:
    """Дети бокса: (тип, начало данных, конец бокса). Читает ровно заголовки.

    ⚠️ Именно генератор, а не список. Заголовок каждого следующего ребёнка лежит за
    предыдущим, то есть «перечислить всех детей» — это дочитать окно до последнего из них.
    У «Моаны 2» от YTS дети ``moov`` — это ``mvhd``, дорожка видео, дорожка звука и
    ``udta``: списком мы вычитывали все 5.26 МБ ради дорожки видео, которая кончается на
    2.08 МБ. Генератор обрывается на первом подошедшем — 2.36 МБ вместо 5.26 (замер
    на «Моане 2» от YTS).
    """
    at = start
    while at + 8 <= end:
        head = window.take(at, 16)
        if len(head) < 8:
            return
        size = struct.unpack(">I", head[:4])[0]
        kind = head[4:8]
        data = at + 8
        if size == 1:  # 64-битный размер: лежит сразу за типом
            if len(head) < 16:
                return
            size = struct.unpack(">Q", head[8:16])[0]
            data = at + 16
        elif size == 0:  # «до конца родителя» - так пишут последний бокс
            size = end - at
        if size < data - at or at + size > end:
            return
        yield kind, data, at + size
        at += size


def _find(window: _Window, start: int, end: int, want: bytes) -> tuple[int, int] | None:
    return next(((a, b) for kind, a, b in _boxes(window, start, end) if kind == want), None)


def _full(window: _Window, data: int) -> tuple[int, int]:
    """Заголовок ``FullBox``: версия и смещение сразу за версией с флагами."""
    return window.take(data, 1)[0], data + 4


def _table(window: _Window, data: int, end: int, width: int) -> tuple[int, int]:
    """Начало и число записей таблицы фиксированной ширины; лишнее не читаем."""
    _, at = _full(window, data)
    count = struct.unpack(">I", window.take(at, 4))[0]
    at += 4
    return at, min(count, max(0, (end - at) // width))
