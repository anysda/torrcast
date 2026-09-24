"""Raster dimensions from poster bytes, without an image-decoding dependency."""

from __future__ import annotations

import struct


def picture_size(body: bytes) -> tuple[int, int] | None:
    """Return ``(width, height)`` for the raster formats served by :mod:`hass.picture_type`."""
    if body.startswith(b"\x89PNG\r\n\x1a\n") and len(body) >= 24:
        return struct.unpack(">II", body[16:24])
    if body.startswith((b"GIF87a", b"GIF89a")) and len(body) >= 10:
        return struct.unpack("<HH", body[6:10])
    if body.startswith(b"\xff\xd8\xff"):
        return _jpeg_size(body)
    if body.startswith(b"RIFF") and body[8:12] == b"WEBP":
        return _webp_size(body)
    return None


def _jpeg_size(body: bytes) -> tuple[int, int] | None:
    """Read the first JPEG start-of-frame marker; scan metadata without decoding pixels."""
    at = 2
    frames = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while at + 3 < len(body):
        if body[at] != 0xFF:
            at += 1
            continue
        while at < len(body) and body[at] == 0xFF:
            at += 1
        if at >= len(body):
            return None
        marker = body[at]
        at += 1
        if marker in {0x01, *range(0xD0, 0xDA)}:
            continue
        if at + 2 > len(body):
            return None
        length = int.from_bytes(body[at : at + 2], "big")
        if length < 2 or at + length > len(body):
            return None
        if marker in frames and length >= 7:
            height = int.from_bytes(body[at + 3 : at + 5], "big")
            width = int.from_bytes(body[at + 5 : at + 7], "big")
            return (width, height) if width and height else None
        at += length
    return None


def _webp_size(body: bytes) -> tuple[int, int] | None:
    """Read dimensions from the three WebP bitstream headers."""
    if len(body) < 30:
        return None
    kind = body[12:16]
    if kind == b"VP8X":
        return 1 + int.from_bytes(body[24:27], "little"), 1 + int.from_bytes(body[27:30], "little")
    if kind == b"VP8 " and body[23:26] == b"\x9d\x01\x2a" and len(body) >= 30:
        width, height = struct.unpack("<HH", body[26:30])
        return width & 0x3FFF, height & 0x3FFF
    if kind == b"VP8L" and body[20:21] == b"/" and len(body) >= 25:
        bits = int.from_bytes(body[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return None


__all__ = ["picture_size"]
