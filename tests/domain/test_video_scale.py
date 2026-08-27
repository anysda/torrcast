"""Шкала дорожки картинки: ею и обязана быть собрана склейка."""

from __future__ import annotations

import struct

from torrcast.domain.video_scale import video_scale


def _box(kind: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def _trak(track: int, scale: int, kind: bytes) -> bytes:
    tkhd = _box(b"tkhd", b"\x00" * 12 + struct.pack(">I", track))
    mdhd = _box(b"mdhd", b"\x00" * 12 + struct.pack(">I", scale))
    hdlr = _box(b"hdlr", b"\x00" * 8 + kind)
    return _box(b"trak", tkhd + _box(b"mdia", mdhd + hdlr))


def test_the_scale_of_the_picture_is_found_by_the_handler_and_not_by_the_number() -> None:
    """Дорожка картинки бывает и второй: «первая - картинка» это догадка, а не свойство файла."""
    head = _box(b"moov", _trak(1, 48000, b"soun") + _trak(2, 16000, b"vide"))

    assert video_scale(head) == 16000


def test_a_head_without_a_picture_at_all_answers_zero() -> None:
    """Картинки в заголовке нет - и шкалы её нет: собрать по ней склейку нечем."""
    assert video_scale(_box(b"moov", _trak(1, 48000, b"soun"))) == 0
