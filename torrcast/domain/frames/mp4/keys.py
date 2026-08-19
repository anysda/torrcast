"""Снятие карты опорных кадров mp4: собрать её из таблиц ``moov``.

Что за таблицы и почему их пять - в докстроке пакета
(:mod:`torrcast.domain.frames.mp4`); здесь сама сборка.
"""

from __future__ import annotations

import struct

from torrcast.domain.frames.keymap.key_map import KeyMap
from torrcast.domain.frames.keymap.point import Point
from torrcast.domain.frames.mp4._moov import (
    _edit_shift,
    _find_moov,
    _media_scale,
    _movie,
    _track_id,
    _video_trak,
)
from torrcast.domain.frames.mp4._tables import (
    _composition,
    _offsets,
    _sample_times,
    _sync_samples,
)
from torrcast.domain.frames.mp4._window import _find, _Window
from torrcast.domain.frames.range_reader import RangeReader as Reader
from torrcast.domain.infra_error import InfraError


def keys(reader: Reader, head: bytes) -> KeyMap:
    """Карта опорных кадров mp4. ``head`` — уже прочитанные байты начала файла.

    Отдаёт точки **только дорожки видео**: ``hdlr`` называет её тип прямо, и угадывать
    дорожку по регулярности точек, как в mkv, здесь не нужно.
    """
    at, size, header = _find_moov(reader, head)
    # Окно отсчитывается от самого бокса, а его дети начинаются сразу за заголовком.
    window = _Window(reader, at, size, head[at:])
    moov = (header, size)
    movie, length = _movie(window, moov)
    trak = _video_trak(window, moov)
    media = _find(window, *trak, b"mdia")
    stbl = _find(window, *media, b"minf") if media else None
    stbl = _find(window, *stbl, b"stbl") if stbl else None
    if media is None or stbl is None:
        raise InfraError("в mp4 нет таблиц дорожки видео (stbl)")
    scale = _media_scale(window, media)
    if not scale:
        raise InfraError("в mp4 не читается масштаб времени дорожки (mdhd)")

    sizes = _find(window, *stbl, b"stsz")
    total = struct.unpack(">I", window.take(sizes[0] + 8, 4))[0] if sizes else 0
    sync = _sync_samples(window, stbl, total)
    if not sync:
        raise InfraError("в mp4 нет ни одного опорного кадра")
    times = _sample_times(window, stbl, sync)
    shift = _edit_shift(window, trak, movie, scale)
    ahead = _composition(window, stbl, sync)
    where = _offsets(window, stbl, sync)
    track = _track_id(window, trak)

    points = [
        Point((clock + ahead.get(number, 0)) / scale - shift, offset, track)
        for number, clock, offset in zip(sync, times, where, strict=False)
    ]
    if not points:
        raise InfraError("таблицы mp4 есть, но карта из них не собралась")
    if length <= 0:
        length = points[-1].at
    return KeyMap(length, tuple(sorted(points)), reader.taken, reader.requests, "mp4")
