"""Карта опорных кадров mkv: разбор индекса ``Cues``.

Что это за индекс и чем он взят - в докстроке пакета
(:mod:`torrcast.domain.frames.mkv`); матрёшку EBML разбирают соседи
(:func:`~torrcast.domain.frames.mkv.walk.walk`, :class:`~torrcast.domain.frames.mkv.head.Head`),
здесь сам индекс.
"""

from __future__ import annotations

from torrcast.domain.frames.keymap import KeyMap, Point
from torrcast.domain.frames.mkv.head import Head
from torrcast.domain.frames.mkv.ids import (
    CUE_CLUSTER_POSITION,
    CUE_POINT,
    CUE_TIME,
    CUE_TRACK,
    CUE_TRACK_POSITIONS,
    CUES,
    CUES_CHUNK,
    HEAD_BYTES,
)
from torrcast.domain.frames.mkv.uint import uint
from torrcast.domain.frames.mkv.walk import walk
from torrcast.domain.frames.range_reader import RangeReader as Reader
from torrcast.domain.infra_error import InfraError


def keys(reader: Reader, head: bytes) -> KeyMap:
    """Карта опорных кадров mkv. ``head`` — уже прочитанные :data:`HEAD_PEEK` байт.

    Заходов к рою ровно два (:data:`~torrcast.adapters.frames.keyframes.HEAD_PEEK` и
    :data:`CUES_CHUNK`), и оба — минимально возможного размера: у холодной раздачи цена
    карты — это не байты, а сколько раз мы заставили рой отдать новое место и сколько ждали
    перед следующим
    запросом.
    """
    facts = Head(head)
    if facts.cues_at is None or facts.duration <= 0:  # маленького куска не хватило
        facts = Head(reader.read(0, HEAD_BYTES))
    if facts.segment is None:
        raise InfraError("это не mkv: элемента Segment в голове файла нет")
    if facts.cues_at is None:
        raise InfraError("в файле нет индекса Cues - карту опорных кадров взять неоткуда")

    chunk = reader.read(facts.cues_at, CUES_CHUNK)
    found = walk(chunk, 0, min(32, len(chunk)))
    if not found:
        raise InfraError("по позиции из SeekHead читается не элемент EBML")
    ident, size, data = found[0]
    if ident != CUES:
        raise InfraError(f"по позиции из SeekHead лежит не Cues, а {ident:#x}")
    body = chunk[data : data + size]
    if len(body) < size:  # редкий толстый индекс - добираем остаток
        body += reader.read(facts.cues_at + len(chunk), size - len(body))

    points = _points(body, facts)
    if not points:
        raise InfraError("Cues в файле есть, но точек в нём нет")
    duration = facts.duration * facts.scale / 1e9
    return KeyMap(duration, tuple(sorted(points)), reader.taken, reader.requests, "mkv")


def _points(body: bytes, facts: Head) -> list[Point]:
    """Точки Cues: время в секундах и **абсолютное** смещение кластера в файле.

    ⚠️ ``CueClusterPosition`` в файле отсчитан от начала данных ``Segment``, а наружу
    смещение обязано быть абсолютным: по нему греется рой под перемотку, а рою всё
    равно, что там за матрёшка, — он знает только байты от начала файла.
    """
    base = facts.segment or 0
    points: list[Point] = []
    for _, point_size, point in [e for e in walk(body, 0, len(body)) if e[0] == CUE_POINT]:
        at = None
        for sub, sub_size, sub_data in walk(body, point, point + point_size):
            if sub == CUE_TIME:
                at = uint(body, sub_data, sub_size) * facts.scale / 1e9
            elif sub == CUE_TRACK_POSITIONS and at is not None:
                offset, track = 0, 0
                for deep, deep_size, deep_data in walk(body, sub_data, sub_data + sub_size):
                    if deep == CUE_CLUSTER_POSITION and not offset:
                        offset = uint(body, deep_data, deep_size)
                    elif deep == CUE_TRACK:
                        track = uint(body, deep_data, deep_size)
                points.append(Point(at, base + offset, track))
    return points
