"""Где в файле ``moov``, что в нём за дорожка видео и как сдвинуто её время.

Зовёт это снятие карты (:func:`torrcast.domain.frames.mp4.keys`) - и только оно.
"""

from __future__ import annotations

import struct
from typing import Final

from torrcast.domain.frames.mp4._window import _boxes, _find, _full, _Window
from torrcast.domain.frames.range_reader import RangeReader as Reader
from torrcast.domain.infra_error import InfraError

#: Сколько верхних боксов пройдём в поисках ``moov``. Их в файле единицы (``ftyp``,
#: ``free``, ``mdat``, ``moov``); полсотни - это уже не mp4, а мусор, и лучше честно
#: сдаться, чем ходить по нему запросами.
MAX_TOP_BOXES: Final = 50


def _find_moov(reader: Reader, head: bytes) -> tuple[int, int, int]:
    """Где в файле лежит ``moov``: начало, размер и длина заголовка.

    Идём шагами по верхним боксам, читая по 16 байт заголовка: ``mdat`` в два гигабайта
    так не читается ни байтом, даже если ``moov`` спрятан за ним в хвосте файла.
    """
    at = 0
    for _ in range(MAX_TOP_BOXES):
        raw = head[at : at + 16] if at + 16 <= len(head) else reader.read(at, 16)
        if len(raw) < 8:
            break
        size = struct.unpack(">I", raw[:4])[0]
        kind = raw[4:8]
        header = 8
        if size == 1:
            if len(raw) < 16:
                break
            size = struct.unpack(">Q", raw[8:16])[0]
            header = 16
        if kind == b"moov":
            return at, size, header
        if size < header:
            break
        at += size
    raise InfraError("в mp4 нет бокса moov - карту опорных кадров взять неоткуда")


def _movie(window: _Window, moov: tuple[int, int]) -> tuple[int, float]:
    """Масштаб времени фильма и его длительность из ``mvhd`` — то же, что печатает ffprobe."""
    found = _find(window, *moov, b"mvhd")
    if found is None:
        return 0, 0.0
    version, at = _full(window, found[0])
    at += 16 if version == 1 else 8  # created/modified
    scale = struct.unpack(">I", window.take(at, 4))[0]
    length = (
        struct.unpack(">Q", window.take(at + 4, 8))[0]
        if version == 1
        else struct.unpack(">I", window.take(at + 4, 4))[0]
    )
    return scale, (length / scale if scale else 0.0)


def _video_trak(window: _Window, moov: tuple[int, int]) -> tuple[int, int]:
    """Дорожка видео: ту, что назвалась ``vide`` в ``hdlr``. Гадать не нужно (mkv — нужно)."""
    for kind, data, end in _boxes(window, *moov):
        if kind != b"trak":
            continue
        media = _find(window, data, end, b"mdia")
        if media is None:
            continue
        handler = _find(window, *media, b"hdlr")
        if handler is not None and window.take(handler[0] + 8, 4) == b"vide":
            return data, end
    raise InfraError("в mp4 нет дорожки видео")


def _track_id(window: _Window, trak: tuple[int, int]) -> int:
    found = _find(window, *trak, b"tkhd")
    if found is None:
        return 1
    version, at = _full(window, found[0])
    at += 16 if version == 1 else 8
    return int(struct.unpack(">I", window.take(at, 4))[0])


def _media_scale(window: _Window, media: tuple[int, int]) -> int:
    found = _find(window, *media, b"mdhd")
    if found is None:
        return 0
    version, at = _full(window, found[0])
    at += 16 if version == 1 else 8
    return int(struct.unpack(">I", window.take(at, 4))[0])


def _edit_shift(window: _Window, trak: tuple[int, int], movie: int, media: int) -> float:
    """Сдвиг из ``elst``, секунды: время наружу = время в файле **минус** этот сдвиг.

    Правки бывают двух видов, и обе встречаются в живых файлах:

    * обычная (``media_time >= 0``) выкидывает начало дорожки — так YTS-релизы срезают
      два кадра (``media_time = 2002`` при масштабе 24000);
    * пустая (``media_time = -1``) наоборот вставляет паузу перед дорожкой — так ffmpeg
      выравнивает видео со звуком, и ремукс mkv в mp4 даёт ровно её (6 мс).

    ⚠️ Пустую правку легко принять за «ничего не делает» и пропустить: она задана не в
    масштабе дорожки, а в масштабе фильма. Пропуск стоил бы 6 мс на всей карте — ровно
    столько, чтобы граница сегмента промахнулась мимо опорного кадра.
    """
    edits = _find(window, *trak, b"edts")
    found = _find(window, *edits, b"elst") if edits else None
    if found is None or not media:
        return 0.0
    version, at = _full(window, found[0])
    count = struct.unpack(">I", window.take(at, 4))[0]
    at += 4
    width = 20 if version == 1 else 12
    delay = 0.0
    for _ in range(min(count, max(0, (found[1] - at) // width))):
        raw = window.take(at, width)
        if version == 1:
            span, start = struct.unpack(">Qq", raw[:16])
        else:
            span, start = struct.unpack(">Ii", raw[:8])
        if start >= 0:
            return float(start) / media - delay
        delay += span / movie if movie else 0.0
        at += width
    return -delay
