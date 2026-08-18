"""Голова mkv: где Segment, где Cues, масштаб времени и длительность фильма."""

from __future__ import annotations

import struct

from torrcast.domain.frames.mkv.ids import (
    CLUSTER,
    CUES,
    DURATION,
    INFO,
    SEEK,
    SEEK_HEAD,
    SEEK_ID,
    SEEK_POSITION,
    SEGMENT,
    TIMESTAMP_SCALE,
)
from torrcast.domain.frames.mkv.uint import uint
from torrcast.domain.frames.mkv.walk import walk


def _float(buf: bytes, data: int, size: int) -> float:
    raw = buf[data : data + size]
    return float(struct.unpack(">f" if size == 4 else ">d", raw)[0])


class Head:
    """Что нужно от головы mkv: где Segment, где Cues, масштаб времени и длительность."""

    __slots__ = ("cues_at", "duration", "scale", "segment")

    def __init__(self, head: bytes) -> None:
        self.segment: int | None = next(
            (data for ident, _, data in walk(head, 0, len(head)) if ident == SEGMENT), None
        )
        self.cues_at: int | None = None
        self.scale = 1_000_000
        self.duration = 0.0
        if self.segment is None:
            return
        for ident, size, data in walk(head, self.segment, len(head)):
            end = min(len(head), data + size)
            if ident == SEEK_HEAD:
                self._seek_head(head, data, end)
            elif ident == INFO:
                self._info(head, data, end)
            elif ident == CLUSTER:
                break  # пошли данные фильма - служебного дальше в голове нет

    def _seek_head(self, head: bytes, data: int, end: int) -> None:
        for _, seek_size, seek in [e for e in walk(head, data, end) if e[0] == SEEK]:
            what = which = None
            for sub, sub_size, sub_data in walk(head, seek, seek + seek_size):
                if sub == SEEK_ID:
                    what = uint(head, sub_data, sub_size)
                elif sub == SEEK_POSITION:
                    which = uint(head, sub_data, sub_size)
            if what == CUES and which is not None and self.segment is not None:
                self.cues_at = self.segment + which

    def _info(self, head: bytes, data: int, end: int) -> None:
        for sub, sub_size, sub_data in walk(head, data, end):
            if sub == TIMESTAMP_SCALE:
                self.scale = uint(head, sub_data, sub_size)
            elif sub == DURATION:
                self.duration = _float(head, sub_data, sub_size)
