"""Сколько тиков в секунде у каждой дорожки заголовка."""

from __future__ import annotations

import struct

from torrcast.domain.tape_scales import tape_scales


def _box(kind: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def _trak(track: int, scale: int, kind: bytes) -> bytes:
    tkhd = _box(b"tkhd", b"\x00" * 12 + struct.pack(">I", track))
    mdhd = _box(b"mdhd", b"\x00" * 12 + struct.pack(">I", scale))
    hdlr = _box(b"hdlr", b"\x00" * 8 + kind)
    return _box(b"trak", tkhd + _box(b"mdia", mdhd + hdlr))


def test_the_scale_of_each_track_is_taken_from_its_own_head() -> None:
    """🔴 Замер: показ пишет картинку шкалой 16000, а склейку тот же ffmpeg - 12288."""
    head = _box(b"moov", _trak(1, 16000, b"vide") + _trak(2, 48000, b"soun"))

    assert tape_scales(head) == {1: 16000, 2: 48000}
