"""Совместимый фасад карты опорных кадров."""

from typing import Final

from torrcast.adapters.frames.http_range_reader import HttpRangeReader as Reader
from torrcast.domain.frames.keymap import KeyMap, Point, video_track
from torrcast.domain.infra_error import InfraError

HEAD_PEEK: Final = 256 << 10


def _keyframes(url: str) -> KeyMap:
    """Читает индекс контейнера диапазонными HTTP-запросами."""
    reader = Reader(url)
    head = reader.read(0, HEAD_PEEK)
    if head[:4] == b"\x1a\x45\xdf\xa3":
        from torrcast.domain.frames.mkv import keys

        return keys(reader, head)
    if head[4:8] in {b"ftyp", b"moov", b"free", b"skip", b"mdat", b"wide"}:
        from torrcast.domain.frames.mp4 import keys

        return keys(reader, head)
    raise InfraError("это не mkv и не mp4: карту опорных кадров взять неоткуда")


keyframes = _keyframes

__all__ = ["HEAD_PEEK", "KeyMap", "Point", "Reader", "keyframes", "video_track"]
