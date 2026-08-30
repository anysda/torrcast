"""Снятие карты опорных кадров mp4: собрать её из таблиц ``moov``.

Что за таблицы и почему их пять - в докстроке пакета
(:mod:`torrcast.domain.frames.mp4`); здесь сама сборка.
"""

from __future__ import annotations

import struct

from torrcast.domain.catalogs.phrase import phrase
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
        raise InfraError(phrase("frames.mp4_no_stbl"))
    scale = _media_scale(window, media)
    if not scale:
        raise InfraError(phrase("frames.mp4_no_mdhd"))

    sizes = _find(window, *stbl, b"stsz")
    total = struct.unpack(">I", window.take(sizes[0] + 8, 4))[0] if sizes else 0
    sync = _sync_samples(window, stbl, total)
    if not sync:
        raise InfraError(phrase("frames.mp4_no_keyframe"))
    times = _sample_times(window, stbl, sync)
    shift = _edit_shift(window, trak, movie, scale)
    ahead = _composition(window, stbl, sync)
    where = _offsets(window, stbl, sync)
    track = _track_id(window, trak)

    # Есть ли у дорожки список правок - решает, по какому времени ffmpeg ИЩЕТ кадр при
    # ``-ss``: со списком его индекс перестроен на метки показа (замер TC-695: ``-ss``
    # ниже суб-мс метки садится на ПРЕЖНИЙ кадр), а без списка индекс стоит на времени
    # декодирования, и в окне между dts и меткой кадра посадка - САМ кадр (замер TC-699
    # на живом YIFY-релизе). Предсказание посадки идёт по исковому времени
    # (:func:`torrcast.adapters.stream_pack.mapped_start.mapped_start`), поэтому без правок
    # его надо отдать картой отдельным рядом.
    edits = _find(window, *trak, b"edts")
    seekable = edits is not None and _find(window, *edits, b"elst") is not None

    pairs = sorted(
        (
            Point((clock + ahead.get(number, 0)) / scale - shift, offset, track),
            clock / scale,
        )
        for number, clock, offset in zip(sync, times, where, strict=False)
    )
    points = tuple(point for point, _decode in pairs)
    via = () if seekable else tuple(decode for _point, decode in pairs)
    if not points:
        raise InfraError(phrase("frames.mp4_map_empty"))
    if length <= 0:
        length = points[-1].at
    return KeyMap(length, points, reader.taken, reader.requests, "mp4", via=via)
