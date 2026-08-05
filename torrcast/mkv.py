"""Карта опорных кадров mkv по HTTP — без скачивания фильма.

Зачем это в пакете, а не в диагностическом скрипте: по этой карте строится **сетка
сегментов** (:class:`torrcast.stream.Grid`). Границы, стоящие на опорных кадрах, дают
сегменты, каждый из которых декодируется сам по себе, — а значит перемотка в любую точку
показывает картинку сразу, а не с ближайшего опорного кадра где-то в середине куска.

Читать ради этого весь фильм нельзя (3–5 ГБ через рой), а ``ffprobe -show_packets``
именно это и делает. Обход: в mkv есть собственный индекс перемотки — элемент ``Cues``.
В нём для каждого опорного кадра лежат время и позиция кластера в байтах, то есть готовая
карта GOP: длительность — разница времён, вес — разница позиций. Cues берётся тремя
Range-запросами (голова файла ради SeekHead, заголовок Cues, тело Cues) и весит единицы
мегабайт. Замер 05-08-2026 на стенде: «Моана 2» (3.4 ГБ, 1119 опорных кадров) — 4.4 МБ и
1.7 с, «Моана» 2016 (4.5 ГБ, 2830 опорных) — 4.4 МБ и 1.0 с.

Работает только с mkv: у mp4 индекс лежит в ``stss``/``stts`` внутри ``moov`` и разбирается
иначе. Не mkv — :class:`~torrcast.InfraError`, и показ честно берёт ровную сетку.

⚠️ Время в Cues — это метка кадра в **середине файла**: ровно те же числа ffmpeg отдаёт
на выходе, когда пакует с ``-ss``. При упаковке от нуля метки всего фильма сдвинуты на
один кадр вперёд (ffmpeg не пускает dts ниже нуля), поэтому сравнивать карту с готовыми
сегментами нужно с допуском в кадр, а не побайтно.
"""

from __future__ import annotations

import itertools
import struct
import urllib.error
import urllib.request
from typing import Final, NamedTuple

from torrcast import InfraError, why

__all__ = ["KeyMap", "Point", "keyframes", "video_track"]

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

#: Сколько головы читаем: SeekHead и Info лежат в самом начале Segment.
HEAD_BYTES: Final = 4 << 20


class Point(NamedTuple):
    """Опорный кадр: время от начала фильма, позиция в байтах, номер дорожки."""

    at: float
    offset: int
    track: int


class KeyMap(NamedTuple):
    """Карта опорных кадров файла и цена её снятия."""

    duration: float
    points: tuple[Point, ...]
    taken: int
    requests: int


class Reader:
    """Range-запросы к одному URL со счётчиком выкачанного — цена замера видна глазами."""

    def __init__(self, url: str, timeout: float = 120.0) -> None:
        self.url = url
        self.timeout = timeout
        self.taken = 0
        self.requests = 0

    def read(self, offset: int, size: int) -> bytes:
        request = urllib.request.Request(
            self.url, headers={"Range": f"bytes={offset}-{offset + size - 1}"}
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as answer:
                data: bytes = answer.read()
        # ValueError — это «источник вообще не URL» (путь к файлу в тестах и на dev).
        # Без неё показ падал бы ещё до упаковки там, где достаточно ровной сетки.
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise InfraError(f"не читается голова файла: {why(exc)}") from exc
        self.taken += len(data)
        self.requests += 1
        return data


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
        # Segment длиной с весь фильм в голову не влез: его дети — да, а вот соседа за
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


def keyframes(url: str) -> KeyMap:
    """Длительность и опорные кадры файла. Не mkv или нет Cues — :class:`InfraError`."""
    reader = Reader(url)
    head = reader.read(0, HEAD_BYTES)
    segment = next((data for ident, _, data in _walk(head, 0, len(head)) if ident == SEGMENT), None)
    if segment is None:
        raise InfraError("это не mkv: элемента Segment в голове файла нет")

    cues_at, scale, duration = None, 1_000_000, 0.0
    for ident, size, data in _walk(head, segment, len(head)):
        end = min(len(head), data + size)
        if ident == SEEK_HEAD:
            for _, seek_size, seek in [e for e in _walk(head, data, end) if e[0] == SEEK]:
                what = which = None
                for sub, sub_size, sub_data in _walk(head, seek, seek + seek_size):
                    if sub == SEEK_ID:
                        what = _uint(head, sub_data, sub_size)
                    elif sub == SEEK_POSITION:
                        which = _uint(head, sub_data, sub_size)
                if what == CUES and which is not None:
                    cues_at = segment + which
        elif ident == INFO:
            for sub, sub_size, sub_data in _walk(head, data, end):
                if sub == TIMESTAMP_SCALE:
                    scale = _uint(head, sub_data, sub_size)
                elif sub == DURATION:
                    duration = _float(head, sub_data, sub_size)
        elif ident == CLUSTER:
            break  # пошли данные фильма — служебного дальше в голове нет
    if cues_at is None:
        raise InfraError("в файле нет индекса Cues — карту опорных кадров взять неоткуда")

    ident, size, data = _walk(reader.read(cues_at, 32), 0, 32)[0]
    if ident != CUES:
        raise InfraError(f"по позиции из SeekHead лежит не Cues, а {ident:#x}")
    body = reader.read(cues_at + data, size)

    points: list[Point] = []
    for _, point_size, point in [e for e in _walk(body, 0, len(body)) if e[0] == CUE_POINT]:
        at = None
        for sub, sub_size, sub_data in _walk(body, point, point + point_size):
            if sub == CUE_TIME:
                at = _uint(body, sub_data, sub_size) * scale / 1e9
            elif sub == CUE_TRACK_POSITIONS and at is not None:
                offset, track = 0, 0
                for deep, deep_size, deep_data in _walk(body, sub_data, sub_data + sub_size):
                    if deep == CUE_CLUSTER_POSITION and not offset:
                        offset = _uint(body, deep_data, deep_size)
                    elif deep == CUE_TRACK:
                        track = _uint(body, deep_data, deep_size)
                points.append(Point(at, offset, track))
    if not points:
        raise InfraError("Cues в файле есть, но точек в нём нет")
    return KeyMap(duration * scale / 1e9, tuple(sorted(points)), reader.taken, reader.requests)


def video_track(points: tuple[Point, ...]) -> int:
    """Дорожка видео: та, чьи точки покрывают фильм без длинных пробелов.

    Cues пишутся и для звука с субтитрами (у «Моаны 2» их шесть), а нас интересует ровно
    та дорожка, по которой ffmpeg будет резать сегменты. ⚠️ «Больше всего точек» —
    неверный признак: у той же «Моаны 2» самая многочисленная дорожка (1786 точек) это
    звук, и пробелы в ней до 65 с, тогда как у видео (1119 точек) — не больше 10.4 с.
    Поэтому берём по самому короткому наибольшему пробелу: у видео опорный кадр обязан
    быть регулярным, у звука точки ставятся как придётся.
    """

    def widest(track: int) -> tuple[float, int]:
        at = [p.at for p in points if p.track == track]
        gaps = [b - a for a, b in itertools.pairwise(at)]
        return (max(gaps, default=float("inf")), -len(at))

    return min({p.track for p in points}, key=widest)
