"""Infohash файла .torrent: sha1 словаря ``info`` ровно в тех байтах, что пришли."""

from __future__ import annotations

import hashlib


def info_hash(data: bytes) -> str | None:
    """Hex infohash описания или ``None``, если это не bencode-словарь с ``info``.

    Хэш считается по сырым байтам словаря, а не по пересобранному: пересборка
    нормализует порядок ключей, и подменённое описание дало бы чужой, но «верный» хэш.
    """
    if data[:1] != b"d":
        return None
    try:
        span = _info_span(data)
    except (ValueError, IndexError, RecursionError):
        return None
    return hashlib.sha1(data[span[0] : span[1]]).hexdigest() if span else None


def _info_span(data: bytes) -> tuple[int, int] | None:
    """Границы значения ключа ``info`` в корневом словаре."""
    pos = 1
    while data[pos : pos + 1] != b"e":
        key_end = _skip(data, pos)
        key = data[data.index(b":", pos) + 1 : key_end]
        value_end = _skip(data, key_end)
        if key == b"info":
            return (key_end, value_end) if data[key_end : key_end + 1] == b"d" else None
        pos = value_end
    return None


def _skip(data: bytes, pos: int) -> int:
    """Позиция сразу за bencode-значением, начатым в ``pos``."""
    head = data[pos : pos + 1]
    if head == b"i":
        return data.index(b"e", pos) + 1
    if head in (b"l", b"d"):
        pos += 1
        while data[pos : pos + 1] != b"e":
            pos = _skip(data, pos)
        return pos + 1
    colon = data.index(b":", pos)
    size = int(data[pos:colon])
    end = colon + 1 + size
    if size < 0 or end > len(data):
        raise ValueError("bencode string runs past the end")
    return end


__all__ = ["info_hash"]
