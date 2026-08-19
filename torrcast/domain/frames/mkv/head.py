"""Голова mkv: где Segment, где Cues, масштаб времени, длительность и дорожка видео."""

from __future__ import annotations

import struct
from typing import Final

from torrcast.domain.frames.mkv.ids import (
    CLUSTER,
    CODEC_ID,
    CUES,
    DURATION,
    INFO,
    SEEK,
    SEEK_HEAD,
    SEEK_ID,
    SEEK_POSITION,
    SEGMENT,
    TIMESTAMP_SCALE,
    TRACK_ENTRY,
    TRACK_NUMBER,
    TRACK_TYPE,
    TRACKS,
)
from torrcast.domain.frames.mkv.uint import uint
from torrcast.domain.frames.mkv.walk import walk

#: ``TrackType`` дорожки видео по списку EBML.
VIDEO: Final = 1


def _float(buf: bytes, data: int, size: int) -> float:
    raw = buf[data : data + size]
    return float(struct.unpack(">f" if size == 4 else ">d", raw)[0])


class Head:
    """Что нужно от головы mkv: где Segment, где Cues, масштаб, длительность, видеодорожка.

    ``video`` и ``codec`` - номер дорожки видео и её кодек по элементу ``Tracks``: файл
    называет свою дорожку сам, и спросить его честнее, чем угадывать дорожку по разрежению
    точек Cues (:func:`~torrcast.domain.frames.keymap.video_track.video_track` остаётся
    запасным путём на случай головы без ``Tracks``).
    """

    __slots__ = ("codec", "cues_at", "duration", "scale", "segment", "video")

    def __init__(self, head: bytes) -> None:
        self.segment: int | None = next(
            (data for ident, _, data in walk(head, 0, len(head)) if ident == SEGMENT), None
        )
        self.cues_at: int | None = None
        self.scale = 1_000_000
        self.duration = 0.0
        self.video: int | None = None
        self.codec = ""
        if self.segment is None:
            return
        for ident, size, data in walk(head, self.segment, len(head)):
            end = min(len(head), data + size)
            if ident == SEEK_HEAD:
                self._seek_head(head, data, end)
            elif ident == INFO:
                self._info(head, data, end)
            elif ident == TRACKS:
                self._tracks(head, data, end)
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

    def _tracks(self, head: bytes, data: int, end: int) -> None:
        """Номер и кодек первой дорожки видео: тип 1 по списку EBML."""
        for _, entry_size, entry in [e for e in walk(head, data, end) if e[0] == TRACK_ENTRY]:
            number = kind = None
            codec = ""
            for sub, sub_size, sub_data in walk(head, entry, entry + entry_size):
                if sub == TRACK_NUMBER:
                    number = uint(head, sub_data, sub_size)
                elif sub == TRACK_TYPE:
                    kind = uint(head, sub_data, sub_size)
                elif sub == CODEC_ID:
                    codec = head[sub_data : sub_data + sub_size].decode("ascii", "replace")
            if kind == VIDEO and number is not None:
                self.video, self.codec = number, codec
                return
