"""Настоящий по форме .torrent для проб: bencode и infohash, как у службы раздач."""

from __future__ import annotations

import hashlib


def bencode(value: object) -> bytes:
    """Закодировать число, строку, байты, список или словарь (ключи по порядку)."""
    if isinstance(value, int):
        return b"i%de" % value
    if isinstance(value, str):
        value = value.encode()
    if isinstance(value, bytes):
        return b"%d:%s" % (len(value), value)
    if isinstance(value, list):
        return b"l" + b"".join(bencode(v) for v in value) + b"e"
    if isinstance(value, dict):
        return b"d" + b"".join(bencode(k) + bencode(value[k]) for k in sorted(value)) + b"e"
    raise TypeError(type(value))


def torrent(name: str = "Cars.2006.mkv", size: int = 7_340_032) -> tuple[str, bytes]:
    """Пара (infohash, байты .torrent) однофайловой раздачи."""
    info = {"length": size, "name": name, "piece length": 262144, "pieces": b"\x01" * 20}
    data = bencode({"announce": "http://tracker.invalid/announce", "info": info})
    return hashlib.sha1(bencode(info)).hexdigest(), data


__all__ = ["bencode", "torrent"]
