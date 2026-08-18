"""Собранная руками матрёшка EBML: ровно те элементы, из которых разбор строит карту.

Настоящего кодирования тут нет намеренно: разбор mkv читает не картинку, а ``SeekHead``,
``Info`` и ``Cues``, - и мера обязана мерить именно их, включая случаи, которых у файла с
ffmpeg не добиться: ``Cues`` не на месте, ``SeekHead`` длиннее первого куска головы.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from torrcast.domain.frames.mkv import (
    CUE_CLUSTER_POSITION,
    CUE_POINT,
    CUE_TIME,
    CUE_TRACK,
    CUE_TRACK_POSITIONS,
    CUES,
    DURATION,
    INFO,
    SEEK,
    SEEK_HEAD,
    SEEK_ID,
    SEEK_POSITION,
    SEGMENT,
    TIMESTAMP_SCALE,
)

EBML_HEADER = 0x1A45DFA3


def ident(value: int) -> bytes:
    """Идентификатор EBML как он лежит в файле - вместе со своим маркером длины."""
    return value.to_bytes((value.bit_length() + 7) // 8, "big")


def length(value: int) -> bytes:
    """Размер элемента восьмибайтовым числом: ширина постоянна, и сборка не пляшет."""
    return b"\x01" + value.to_bytes(7, "big")


def elem(kind: int, payload: bytes) -> bytes:
    """Элемент EBML: идентификатор, размер, тело."""
    return ident(kind) + length(len(payload)) + payload


def uint(value: int) -> bytes:
    """Беззнаковое число EBML восемью байтами."""
    return value.to_bytes(8, "big")


@dataclass(slots=True)
class Matroska:
    """Из чего собирается пробный mkv; умолчания - самый простой годный файл."""

    #: Масштаб времени в наносекундах на единицу (``TimestampScale``).
    scale: int = 1_000_000
    #: Длительность в единицах масштаба (``Duration``).
    duration: float = 6000.0
    #: Точки ``Cues``: ``(время в единицах масштаба, позиция кластера, дорожка)``.
    cues: list[tuple[int, int, int]] = field(default_factory=lambda: [(0, 100, 1), (500, 4000, 1)])
    #: Сколько набивки лежит перед ``Cues``: она отодвигает их за первый кусок головы.
    padding: int = 64
    #: ``SeekHead`` без записи о ``Cues``: адрес индекса взять неоткуда.
    forget_cues: bool = False

    def _cues(self) -> bytes:
        points = b""
        for at, offset, track in self.cues:
            inside = elem(CUE_TRACK, uint(track)) + elem(CUE_CLUSTER_POSITION, uint(offset))
            points += elem(CUE_POINT, elem(CUE_TIME, uint(at)) + elem(CUE_TRACK_POSITIONS, inside))
        return elem(CUES, points)

    def _seek_head(self, at: int) -> bytes:
        if self.forget_cues:
            return elem(SEEK_HEAD, b"")
        seek = elem(SEEK_ID, ident(CUES)) + elem(SEEK_POSITION, uint(at))
        return elem(SEEK_HEAD, elem(SEEK, seek))

    def _info(self) -> bytes:
        body = elem(TIMESTAMP_SCALE, uint(self.scale)) + elem(
            DURATION, struct.pack(">d", self.duration)
        )
        return elem(INFO, body)

    def bytes(self) -> tuple[bytes, int]:
        """Файл целиком и абсолютное смещение данных ``Segment`` в нём."""
        body = self._info() + b"\x00" * self.padding
        # Ширина размеров постоянна, поэтому адрес Cues считается с первой же сборки.
        at = len(self._seek_head(0)) + len(body)
        payload = self._seek_head(at) + body + self._cues()
        head = elem(EBML_HEADER, b"\x00" * 8)
        segment = ident(SEGMENT) + length(len(payload)) + payload
        return head + segment, len(head) + len(ident(SEGMENT)) + 8
