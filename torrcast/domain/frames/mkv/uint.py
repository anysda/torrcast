"""Целое EBML: столько-то байт подряд, старшим вперёд."""

from __future__ import annotations


def uint(buf: bytes, data: int, size: int) -> int:
    """Беззнаковое целое EBML из ``size`` байт по смещению ``data``."""
    return int.from_bytes(buf[data : data + size], "big")
