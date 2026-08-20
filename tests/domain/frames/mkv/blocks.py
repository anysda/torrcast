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
    CUE_RELATIVE_POSITION,
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
from torrcast.domain.frames.mkv.key_frame import BLOCK_BYTES

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
    #: Край окна чтения режет заголовок блока пополам, а видеоблока в окне нет (TC-687).
    cut_header: bool = False
    #: Сколько видеокадров лежит в кластере ПЕРЕД тем, который назвала точка Cues. Они
    #: нарочно противоположны названному по опорности: так видно, чей кадр судит
    #: проверка честности - названный точкой или первый попавшийся в кластере.
    before: int = 0
    #: Муксер назвал место блока внутри кластера (``CueRelativePosition``).
    relative: bool = False

    def inside(self) -> int:
        """Смещение названного блока от начала данных кластера; ноль - муксер смолчал."""
        if not self.relative:
            return 0
        return len(elem(TIMESTAMP, uint(0))) + self.before * len(self._block(1, idr=self.ghost))

    def _cues(self) -> bytes:
        points = b""
        for at, offset, track in self.cues:
            where = elem(CUE_TRACK, uint(track)) + elem(CUE_CLUSTER_POSITION, uint(offset))
            if self.relative:
                where += elem(CUE_RELATIVE_POSITION, uint(self.inside()))
            points += elem(CUE_POINT, elem(CUE_TIME, uint(at)) + elem(CUE_TRACK_POSITIONS, where))
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

    def _block(self, track: int, idr: bool) -> bytes:
        """Блок дорожки с настоящим срезом AVC внутри: IDR (NAL типа 5) или обычный."""
        flags = 0x80 | (0x06 if self.laced else 0)
        frame = (5).to_bytes(4, "big") + (b"\x65" if idr else b"\x41") + b"\x00" * 4
        return elem(SIMPLE_BLOCK, bytes([0x80 | track]) + b"\x00\x00" + bytes([flags]) + frame)

    def _cluster(self, at: int, tracks: list[int]) -> bytes:
        """Кластер: набивка чужих видеокадров, затем по блоку на каждую дорожку точки."""
        if self.cut_header:
            return self._cut_cluster(at)
        payload = elem(TIMESTAMP, uint(at)) + self._block(1, idr=self.ghost) * self.before
        for track in tracks:
            payload += self._block(track, idr=not self.ghost)
        return elem(CLUSTER, payload)

    def _cut_cluster(self, at: int) -> bytes:
        """Кластер, у которого край окна чтения лёг поперёк заголовка блока.

        Блока видеодорожки в окне нет: его место занимает один длинный блок звуковой
        дорожки, а заголовок следующего обрублен краем окна так, что идентификатор
        прочитался целиком, а смещение тела оказалось уже за границей буфера. Бывает
        у живых файлов, и разбор обязан ответить «не разобрать», а не упасть.
        """
        payload = elem(TIMESTAMP, uint(at))
        audio = bytes([0x80 | 2]) + b"\x00\x00" + b"\x80"  # звуковая дорожка, флаг опорности
        room = (
            BLOCK_BYTES
            - len(ident(CLUSTER) + length(0))
            - len(payload)
            - len(ident(SIMPLE_BLOCK) + length(0))
            - 2  # обрубленный заголовок: байт идентификатора и первый байт размера
        )
        payload += elem(SIMPLE_BLOCK, audio + b"\x00" * (room - len(audio)))
        payload += ident(SIMPLE_BLOCK) + b"\x40"
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
