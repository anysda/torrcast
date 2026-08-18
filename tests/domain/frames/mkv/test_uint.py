"""Зеркало :mod:`torrcast.domain.frames.mkv.uint`: целое EBML из байт файла."""

from __future__ import annotations

from torrcast.domain.frames.mkv.uint import uint


def test_the_bytes_are_read_big_endian_from_the_offset() -> None:
    """Старший байт первый, и читаются ровно ``size`` байт от ``data``."""
    buf = b"\xff\x01\x02\x03\xff"
    assert uint(buf, 1, 3) == 0x010203
    assert uint(buf, 1, 0) == 0, "нулевой размер - это ноль, а не исключение"
