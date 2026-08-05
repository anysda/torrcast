"""Карта ключевых кадров mkv по HTTP — без скачивания фильма.

Зачем: спор о нарезке HLS (§6 SPEC-v2) решается только цифрами про КОНКРЕТНЫЙ файл —
где лежат опорные кадры, какой GOP самый длинный и самый тяжёлый, какие сегменты сетка
режет. Читать ради этого весь фильм нельзя (3–5 ГБ через рой), а ``ffprobe -show_packets``
именно это и делает.

Обход: в mkv есть собственный индекс перемотки — элемент ``Cues``. В нём для каждого
опорного кадра лежат время и позиция кластера в байтах, то есть готовая карта GOP:
длительность — разница времён, вес — разница позиций. Cues берётся тремя Range-запросами
(голова файла ради SeekHead, заголовок Cues, тело Cues) и весит единицы мегабайт.
Замер 05-08-2026 на стенде: «Моана 2» (3.4 ГБ, 1119 опорных кадров) — 4.4 МБ и 1.7 с.

Работает только с mkv: у mp4 индекс лежит в ``stss``/``stts`` внутри ``moov`` и разбирается
иначе. Не mkv — скрипт честно говорит об этом и молчать не пытается.

    python3 scripts/keyframes.py "http://127.0.0.1:8090/stream?link=<hash>&index=1&play"
    python3 scripts/keyframes.py <url> --grid 10   # ещё и что творит сетка 10 с
"""

from __future__ import annotations

import argparse
import itertools
import statistics
import struct
import urllib.request
from typing import Final, NamedTuple

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
        with urllib.request.urlopen(request, timeout=self.timeout) as answer:
            data: bytes = answer.read()
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


def keyframes(url: str) -> tuple[float, tuple[Point, ...]]:
    """Длительность и опорные кадры файла: ``(секунды, точки)``."""
    reader = Reader(url)
    head = reader.read(0, HEAD_BYTES)
    segment = next((data for ident, _, data in _walk(head, 0, len(head)) if ident == SEGMENT), None)
    if segment is None:
        raise SystemExit("это не mkv: элемента Segment в голове файла нет")

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
        raise SystemExit("в файле нет индекса Cues — карту опорных кадров взять неоткуда")

    ident, size, data = _walk(reader.read(cues_at, 32), 0, 32)[0]
    if ident != CUES:
        raise SystemExit(f"по позиции из SeekHead лежит не Cues, а {ident:#x}")
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
    print(f"взято {reader.taken / 1e6:.1f} МБ за {reader.requests} запроса, точек {len(points)}")
    return duration * scale / 1e9, tuple(sorted(points))


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


def report(duration: float, points: tuple[Point, ...], grid: int) -> None:
    """Что важно знать про файл перед нарезкой: длина GOP, вес GOP и что творит сетка."""
    track = video_track(points)
    frames = [p for p in points if p.track == track]
    gops = [
        (frames[i].at, frames[i + 1].at - frames[i].at, frames[i + 1].offset - frames[i].offset)
        for i in range(len(frames) - 1)
    ]
    lengths = [g[1] for g in gops]
    print(f"дорожка видео {track}: опорных кадров {len(frames)}, фильм {duration:.0f} с")
    print(
        f"GOP: медиана {statistics.median(lengths):.2f} с, "
        f"самый длинный {max(lengths):.2f} с, самый тяжёлый {max(g[2] for g in gops) / 1e6:.2f} МБ"
    )
    for what, key in (("длинных", lambda g: g[1]), ("тяжёлых", lambda g: g[2])):
        print(f"  пятёрка самых {what}:")
        for at, span, weight in sorted(gops, key=key)[-5:][::-1]:
            print(
                f"    {int(at) // 60}:{int(at) % 60:02d} — {span:5.2f} с, {weight / 1e6:6.2f} МБ, "
                f"{weight * 8 / span / 1e6:5.1f} Мбит/с"
            )
    if grid <= 0:
        return
    cut = sum(1 for at, span, _ in gops if int(at // grid) != int((at + span - 1e-6) // grid))
    slots = int(duration // grid) + 1
    empty = slots - len({int(f.at // grid) for f in frames})
    print(f"сетка {grid} с: сегментов {slots}, GOP разрезано {cut} из {len(gops)}")
    print(f"  сегментов без единого опорного кадра: {empty}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="HTTP-адрес mkv (например, поток TorrServer)")
    parser.add_argument("--grid", type=int, default=0, metavar="СЕК", help="проверить сетку СЕК")
    args = parser.parse_args()
    duration, points = keyframes(args.url)
    report(duration, points, args.grid)


if __name__ == "__main__":
    main()
