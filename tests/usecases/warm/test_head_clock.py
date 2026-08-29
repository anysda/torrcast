"""Дорожка картинки и её шкала из заголовка показа: по ``hdlr``, один раз на файл."""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

from torrcast.usecases.warm.head_clock import head_clock

if TYPE_CHECKING:
    from pathlib import Path


def box(kind: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def trak(track: int, scale: int, kind: bytes, *, wide: bool = False) -> bytes:
    """Дорожка заголовка: номер в ``tkhd``, шкала в ``mdhd``, ремесло в ``hdlr``."""
    version = b"\x01" if wide else b"\x00"
    times = b"\x00" * (16 if wide else 8)
    tkhd = box(b"tkhd", version + b"\x00\x00\x00" + times + struct.pack(">I", track))
    mdhd = box(b"mdhd", version + b"\x00\x00\x00" + times + struct.pack(">I", scale))
    hdlr = box(b"hdlr", b"\x00" * 8 + kind)
    return box(b"trak", tkhd + box(b"mdia", mdhd + hdlr))


def head(*traks: bytes) -> bytes:
    return box(b"ftyp", b"iso6") + box(b"moov", b"".join(traks))


def test_the_picture_track_is_found_by_its_craft_and_not_by_its_place(tmp_path: Path) -> None:
    """🔴 Порядок дорожек не обещан никем: звук бывает первым, и мерить им картинку нельзя."""
    init = tmp_path / "init.mp4"
    init.write_bytes(head(trak(1, 44100, b"soun"), trak(2, 24000, b"vide")))

    assert head_clock(init) == (2, 24000)


def test_a_wide_track_header_moves_the_number_by_its_own_version(tmp_path: Path) -> None:
    """У версии 1 времена по восемь байт: смещение номера считается, а не берётся константой."""
    init = tmp_path / "init.mp4"
    init.write_bytes(head(trak(7, 16000, b"vide", wide=True)))

    assert head_clock(init) == (7, 16000)


def test_a_header_without_a_picture_track_answers_nothing(tmp_path: Path) -> None:
    """Одна дорожка звука - переводить счётчик картинки не во что, и гадать тут нельзя."""
    init = tmp_path / "init.mp4"
    init.write_bytes(head(trak(1, 48000, b"soun")))

    assert head_clock(init) == (0, 0)


def test_a_missing_header_is_not_an_error_but_a_nothing(tmp_path: Path) -> None:
    """Заголовка рядом нет - ответ пустой: показ на mpegts кладёт куски вовсе без него."""
    assert head_clock(tmp_path / "нет.mp4") == (0, 0)


def test_the_header_is_read_once_and_reread_when_it_changes(tmp_path: Path) -> None:
    """🔴 Разбор стоит на горячем пути: заголовок читается раз, но перепаковку обязан заметить."""
    init = tmp_path / "init.mp4"
    init.write_bytes(head(trak(1, 24000, b"vide")))
    assert head_clock(init) == (1, 24000)

    init.write_bytes(head(trak(3, 12288, b"vide"), trak(4, 48000, b"soun")))

    assert head_clock(init) == (3, 12288), "перепакованный показ мерят шкалой прошлого заголовка"
