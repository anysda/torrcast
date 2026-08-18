"""Собранный руками mp4: боксы ISO BMFF ровно те, из которых разбор строит карту.

Настоящего кодирования тут нет намеренно. Разбор mp4 читает не картинку, а пять таблиц
``moov``, и мера обязана мерить именно их - в том числе те случаи, которых у готового
файла с ffmpeg не добиться: список правок с ненулевым ``media_time``, ``moov`` за
``mdat``, отсутствующий ``stss``.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field


def box(kind: bytes, payload: bytes) -> bytes:
    """Бокс ISO BMFF: размер, тип, тело."""
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def full(payload: bytes, version: int = 0) -> bytes:
    """Тело ``FullBox``: версия, флаги, дальше содержимое."""
    return bytes([version]) + b"\x00\x00\x00" + payload


def table(kind: bytes, rows: list[tuple[int, ...]], width: str) -> bytes:
    """Таблица фиксированной ширины: заголовок ``FullBox``, счётчик, записи."""
    body = b"".join(struct.pack(f">{width}", *row) for row in rows)
    return box(kind, full(struct.pack(">I", len(rows)) + body))


@dataclass(slots=True)
class Movie:
    """Из чего собирается пробный mp4; умолчания - самый простой годный файл."""

    #: Масштаб времени фильма и его длительность в этом масштабе (``mvhd``).
    movie_scale: int = 1000
    movie_length: int = 6000
    #: Масштаб времени дорожки (``mdhd``): в нём считаны времена сэмплов.
    media_scale: int = 600
    track_id: int = 1
    #: ``(segment_duration, media_time)`` списка правок; ``None`` - ``elst`` нет вовсе.
    edit: tuple[int, int] | None = None
    #: Номера опорных сэмплов (``stss``); пусто - таблицы нет, опорный каждый.
    sync: list[int] = field(default_factory=lambda: [1, 3])
    #: Сжатая ``stts``: сколько сэмплов подряд по столько-то единиц.
    times: list[tuple[int, int]] = field(default_factory=lambda: [(4, 150)])
    #: Сжатая ``stsc``: первый чанк, сэмплов в чанке, номер описания.
    chunks: list[tuple[int, int, int]] = field(default_factory=lambda: [(1, 1, 1)])
    #: Смещения чанков (``stco``).
    offsets: list[int] = field(default_factory=lambda: [1000, 2000, 3000, 4000])
    #: Размер сэмпла и их число (``stsz`` с общим размером).
    sample_size: int = 100
    sample_count: int = 4
    #: Сдвиги вывода (``ctts``); пусто - таблицы нет.
    composition: list[tuple[int, int]] = field(default_factory=list)
    #: Перед дорожкой видео лежит дорожка звука: разбор обязан пройти мимо неё.
    sound_first: bool = False
    #: ``moov`` уезжает за ``mdat``, как у файла, не готовленного под сеть.
    moov_last: bool = False
    #: Сколько байт занимает ``mdat``: его разбор не имеет права прочитать.
    mdat_size: int = 4096

    def stbl(self) -> bytes:
        tables = [
            box(b"stsz", full(struct.pack(">II", self.sample_size, self.sample_count))),
            table(b"stts", [tuple(row) for row in self.times], "II"),
            table(b"stsc", [tuple(row) for row in self.chunks], "III"),
            table(b"stco", [(value,) for value in self.offsets], "I"),
        ]
        if self.sync:
            tables.append(table(b"stss", [(number,) for number in self.sync], "I"))
        if self.composition:
            tables.append(table(b"ctts", [tuple(row) for row in self.composition], "Ii"))
        return box(b"stbl", b"".join(tables))

    def trak(self) -> bytes:
        media = box(b"mdia", b"".join([
            box(b"mdhd", full(b"\x00" * 8 + struct.pack(">I", self.media_scale))),
            box(b"hdlr", full(b"\x00" * 4 + b"vide" + b"\x00" * 12)),
            box(b"minf", self.stbl()),
        ]))  # fmt: skip
        parts = [box(b"tkhd", full(b"\x00" * 8 + struct.pack(">I", self.track_id)))]
        if self.edit is not None:
            span, start = self.edit
            entry = struct.pack(">I", 1) + struct.pack(">Iii", span, start, 65536)
            parts.append(box(b"edts", box(b"elst", full(entry))))
        parts.append(media)
        return box(b"trak", b"".join(parts))

    def sound(self) -> bytes:
        """Дорожка звука: те же боксы, но ``hdlr`` называет её ``soun``."""
        media = box(b"mdia", box(b"hdlr", full(b"\x00" * 4 + b"soun" + b"\x00" * 12)))
        return box(b"trak", box(b"tkhd", full(b"\x00" * 8 + struct.pack(">I", 9))) + media)

    def moov(self) -> bytes:
        head = full(b"\x00" * 8 + struct.pack(">II", self.movie_scale, self.movie_length))
        parts = [box(b"mvhd", head)]
        if self.sound_first:
            parts.append(self.sound())
        parts.append(self.trak())
        return box(b"moov", b"".join(parts))

    def bytes(self) -> bytes:
        """Файл целиком: ``ftyp``, ``mdat`` с мусором и ``moov`` с той стороны от него."""
        head = box(b"ftyp", b"isom" + b"\x00" * 8)
        mdat = box(b"mdat", b"\x00" * self.mdat_size)
        return head + (mdat + self.moov() if self.moov_last else self.moov() + mdat)


@dataclass(slots=True)
class Served:
    """Файл в памяти, отданный кусками, как рой: каждый запрос записан."""

    data: bytes
    taken: int = 0
    requests: int = 0
    asked: list[tuple[int, int]] = field(default_factory=list)

    def read(self, offset: int, size: int) -> bytes:
        self.asked.append((offset, size))
        chunk = self.data[offset : offset + size]
        self.taken += len(chunk)
        self.requests += 1
        return chunk
