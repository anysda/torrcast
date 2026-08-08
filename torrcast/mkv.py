"""Карта опорных кадров mkv: индекс ``Cues``.

Общее для всех контейнеров — в :mod:`torrcast.keymap`, там же и вход
(:func:`torrcast.keymap.keyframes`). Здесь только матрёшка EBML.

В mkv есть собственный индекс перемотки — элемент ``Cues``. В нём для каждого опорного
кадра лежат время и позиция кластера в байтах, то есть готовая карта GOP: длительность —
разница времён, вес — разница позиций. Лежит он в хвосте файла, а его адрес — в
``SeekHead`` в голове. Замер: «Моана 2» (3.4 ГБ, 1119 опорных кадров) — 0.45 МБ и
4.3 с холодным роем, «Моана» 2016 (4.5 ГБ, 2830 опорных) — 2.1 с.
"""

from __future__ import annotations

import struct
from typing import Final

from torrcast import InfraError
from torrcast.keymap import KeyMap, Point, Reader

__all__ = ["CUES_CHUNK", "HEAD_BYTES", "keys"]

#: EBML-идентификаторы, которые нам нужны (вместе с маркером длины, как в файле).
SEGMENT: Final = 0x18538067
SEEK_HEAD: Final = 0x114D9B74
SEEK: Final = 0x4DBB
SEEK_ID: Final = 0x53AB
SEEK_POSITION: Final = 0x53AC
INFO: Final = 0x1549A966
TIMESTAMP_SCALE: Final = 0x2AD7B1
DURATION: Final = 0x4489
CLUSTER: Final = 0x1F43B675
CUES: Final = 0x1C53BB6B
CUE_POINT: Final = 0xBB
CUE_TIME: Final = 0xB3
CUE_TRACK_POSITIONS: Final = 0xB7
CUE_TRACK: Final = 0xF7
CUE_CLUSTER_POSITION: Final = 0xF1

#: Запасной размер головы: :data:`~torrcast.keymap.HEAD_PEEK` не хватило (длинный
#: SeekHead, толстые теги).
HEAD_BYTES: Final = 4 << 20
#: Сколько берём с места Cues одним куском. Тело Cues - сотни килобайт (замерено: 163,
#: 189 и 456 КБ), поэтому оно влезает целиком, и хвост стоит **одного** запроса вместо
#: двух: заголовок и тело раньше читались порознь, а холодный рой платит за каждый заход.
CUES_CHUNK: Final = 1 << 20


def _vint(buf: bytes, i: int, keep_marker: bool) -> tuple[int, int]:
    """EBML-число переменной длины: идентификатор читается с маркером, размер — без."""
    head = buf[i]
    if head == 0:
        raise ValueError("битое число EBML")
    width, mask = 1, 0x80
    while not head & mask:
        mask >>= 1
        width += 1
    raw = buf[i : i + width]
    if keep_marker:
        return int.from_bytes(raw, "big"), i + width
    value = head & (mask - 1)
    for byte in raw[1:]:
        value = value << 8 | byte
    return value, i + width


def _walk(buf: bytes, start: int, end: int) -> list[tuple[int, int, int]]:
    """Дети EBML-элемента: (идентификатор, размер, смещение данных)."""
    found: list[tuple[int, int, int]] = []
    i = start
    while i < end:
        try:
            ident, after = _vint(buf, i, keep_marker=True)
            size, data = _vint(buf, after, keep_marker=False)
        except (ValueError, IndexError):
            return found
        found.append((ident, size, data))
        # Segment длиной с весь фильм в голову не влез: его дети - да, а вот соседа за
        # ним в этом куске уже нет, и шагать туда вслепую нельзя.
        if data + size > len(buf):
            return found
        i = data + size
    return found


def _uint(buf: bytes, data: int, size: int) -> int:
    return int.from_bytes(buf[data : data + size], "big")


def _float(buf: bytes, data: int, size: int) -> float:
    raw = buf[data : data + size]
    return float(struct.unpack(">f" if size == 4 else ">d", raw)[0])


class _Head:
    """Что нужно от головы mkv: где Segment, где Cues, масштаб времени и длительность."""

    __slots__ = ("cues_at", "duration", "scale", "segment")

    def __init__(self, head: bytes) -> None:
        self.segment: int | None = next(
            (data for ident, _, data in _walk(head, 0, len(head)) if ident == SEGMENT), None
        )
        self.cues_at: int | None = None
        self.scale = 1_000_000
        self.duration = 0.0
        if self.segment is None:
            return
        for ident, size, data in _walk(head, self.segment, len(head)):
            end = min(len(head), data + size)
            if ident == SEEK_HEAD:
                self._seek_head(head, data, end)
            elif ident == INFO:
                self._info(head, data, end)
            elif ident == CLUSTER:
                break  # пошли данные фильма - служебного дальше в голове нет

    def _seek_head(self, head: bytes, data: int, end: int) -> None:
        for _, seek_size, seek in [e for e in _walk(head, data, end) if e[0] == SEEK]:
            what = which = None
            for sub, sub_size, sub_data in _walk(head, seek, seek + seek_size):
                if sub == SEEK_ID:
                    what = _uint(head, sub_data, sub_size)
                elif sub == SEEK_POSITION:
                    which = _uint(head, sub_data, sub_size)
            if what == CUES and which is not None and self.segment is not None:
                self.cues_at = self.segment + which

    def _info(self, head: bytes, data: int, end: int) -> None:
        for sub, sub_size, sub_data in _walk(head, data, end):
            if sub == TIMESTAMP_SCALE:
                self.scale = _uint(head, sub_data, sub_size)
            elif sub == DURATION:
                self.duration = _float(head, sub_data, sub_size)


def keys(reader: Reader, head: bytes) -> KeyMap:
    """Карта опорных кадров mkv. ``head`` — уже прочитанные :data:`HEAD_PEEK` байт.

    Заходов к рою ровно два (:data:`~torrcast.keymap.HEAD_PEEK` и :data:`CUES_CHUNK`), и
    оба — минимально возможного размера: у холодной раздачи цена карты — это не байты, а
    сколько раз мы заставили рой отдать новое место и сколько ждали перед следующим
    запросом.
    """
    facts = _Head(head)
    if facts.cues_at is None or facts.duration <= 0:  # маленького куска не хватило
        facts = _Head(reader.read(0, HEAD_BYTES))
    if facts.segment is None:
        raise InfraError("это не mkv: элемента Segment в голове файла нет")
    if facts.cues_at is None:
        raise InfraError("в файле нет индекса Cues - карту опорных кадров взять неоткуда")

    chunk = reader.read(facts.cues_at, CUES_CHUNK)
    found = _walk(chunk, 0, min(32, len(chunk)))
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


def _points(body: bytes, facts: _Head) -> list[Point]:
    """Точки Cues: время в секундах и **абсолютное** смещение кластера в файле.

    ⚠️ ``CueClusterPosition`` в файле отсчитан от начала данных ``Segment``, а наружу
    смещение обязано быть абсолютным: по нему греется рой под перемотку, а рою всё
    равно, что там за матрёшка, — он знает только байты от начала файла.
    """
    base = facts.segment or 0
    points: list[Point] = []
    for _, point_size, point in [e for e in _walk(body, 0, len(body)) if e[0] == CUE_POINT]:
        at = None
        for sub, sub_size, sub_data in _walk(body, point, point + point_size):
            if sub == CUE_TIME:
                at = _uint(body, sub_data, sub_size) * facts.scale / 1e9
            elif sub == CUE_TRACK_POSITIONS and at is not None:
                offset, track = 0, 0
                for deep, deep_size, deep_data in _walk(body, sub_data, sub_data + sub_size):
                    if deep == CUE_CLUSTER_POSITION and not offset:
                        offset = _uint(body, deep_data, deep_size)
                    elif deep == CUE_TRACK:
                        track = _uint(body, deep_data, deep_size)
                points.append(Point(at, base + offset, track))
    return points
