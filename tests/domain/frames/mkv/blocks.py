"""Собранная руками матрёшка EBML: ровно те элементы, из которых разбор строит карту.

Настоящего кодирования тут нет намеренно: разбор mkv читает не картинку, а ``SeekHead``,
``Info``, ``Tracks`` и ``Cues``, - и мера обязана мерить именно их, включая случаи,
которых у файла с ffmpeg не добиться: ``Cues`` не на месте, ``SeekHead`` длиннее первого
куска головы, индекс, врущий об опорности каждого кадра (``ghost``).

Кластеры по смещениям из ``Cues`` настоящие: проверка честности индекса
(:func:`~torrcast.domain.frames.mkv.key_frame.key_frame`) читает первый видеоблок и судит
по срезу AVC, поэтому блок несёт настоящий NAL - IDR (тип 5) у честного файла.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from torrcast.domain.frames.mkv.ids import (
    CLUSTER,
    CODEC_ID,
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
    SIMPLE_BLOCK,
    TIMESTAMP_SCALE,
    TRACK_ENTRY,
    TRACK_NUMBER,
    TRACK_TYPE,
    TRACKS,
)

EBML_HEADER = 0x1A45DFA3
#: EBML-идентификаторы, которых нет в ids.py: разбору они не нужны, нужны сборке.
TIMESTAMP = 0xE7
#: Кодеки пробных дорожек, как пишет их ``CodecID``.
AVC = "V_MPEG4/ISO/AVC"
AC3 = "A_AC3"


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
    #: Позиции отсчитаны от начала данных ``Segment``, и по ним обязаны лежать кластеры.
    cues: list[tuple[int, int, int]] = field(default_factory=lambda: [(0, 1024, 1), (500, 4096, 1)])
    #: Дорожки ``Tracks``: ``(номер, тип)``; тип 1 - видео (AVC), остальные - звук (AC3).
    tracks: list[tuple[int, int]] = field(default_factory=lambda: [(1, 1), (2, 2)])
    #: Сколько набивки лежит перед ``Cues``: она отодвигает их за первый кусок головы.
    padding: int = 64
    #: ``SeekHead`` без записи о ``Cues``: адрес индекса взять неоткуда.
    forget_cues: bool = False
    #: ``Tracks`` нет вовсе: дорожку видео придётся угадывать эвристикой.
    forget_tracks: bool = False
    #: Индекс врёт: блок по каждой точке - не IDR, хотя флаг опорности стоит.
    ghost: bool = False
    #: Блоки со включённым лейсингом: содержимое кадра не разобрать.
    laced: bool = False

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

    def _tracks(self) -> bytes:
        if self.forget_tracks:
            return b""
        entries = b""
        for number, kind in self.tracks:
            codec = AVC if kind == 1 else AC3
            entry = (
                elem(TRACK_NUMBER, uint(number))
                + elem(TRACK_TYPE, uint(kind))
                + elem(CODEC_ID, codec.encode("ascii"))
            )
            entries += elem(TRACK_ENTRY, entry)
        return elem(TRACKS, entries)

    def _cluster(self, at: int, tracks: list[int]) -> bytes:
        """Кластер с одним блоком на дорожку; у видео - AVC-срез, IDR или нет."""
        payload = elem(TIMESTAMP, uint(at))
        for track in tracks:
            flags = 0x80 | (0x06 if self.laced else 0)
            nal = b"\x41" if self.ghost else b"\x65"
            frame = (5).to_bytes(4, "big") + nal + b"\x00" * 4
            block = bytes([0x80 | track]) + b"\x00\x00" + bytes([flags]) + frame
            payload += elem(SIMPLE_BLOCK, block)
        return elem(CLUSTER, payload)

    def bytes(self) -> tuple[bytes, int]:
        """Файл целиком и абсолютное смещение данных ``Segment`` в нём."""
        body = self._info() + self._tracks() + b"\x00" * self.padding
        # Ширина размеров постоянна, поэтому адрес Cues считается с первой же сборки.
        at = len(self._seek_head(0)) + len(body)
        payload = self._seek_head(at) + body + self._cues()
        by_offset: dict[int, list[tuple[int, int]]] = {}
        for cue_at, offset, track in self.cues:
            by_offset.setdefault(offset, []).append((cue_at, track))
        for offset in sorted(by_offset):
            if offset < len(payload):
                raise ValueError(f"точка Cues ссылается внутрь головы: {offset}")
            payload += b"\x00" * (offset - len(payload))
            found = by_offset[offset]
            payload += self._cluster(found[0][0], sorted({t for _, t in found}))
        head = elem(EBML_HEADER, b"\x00" * 8)
        segment = ident(SEGMENT) + length(len(payload)) + payload
        return head + segment, len(head) + len(ident(SEGMENT)) + 8
