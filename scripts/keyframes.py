"""Карта опорных кадров по HTTP — отчёт по файлу перед нарезкой.

Разбор индексов живёт в пакете (:mod:`torrcast.domain.frames.keymap`): по этой же карте показ строит
сетку
сегментов, и двух реализаций у неё быть не должно. Здесь остаётся то, ради чего скрипт
запускают руками, — человеческий отчёт: длина и вес GOP, что с ними делает сетка.

    python3 scripts/keyframes.py "http://127.0.0.1:8090/stream?link=<hash>&index=1&play"
    python3 scripts/keyframes.py <url> --grid 10   # ещё и что творит сетка 10 с
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast import TorrcastError
from torrcast.adapters.frames.keyframes import keyframes
from torrcast.domain.frames.keymap import Point, video_track


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
                f"    {int(at) // 60}:{int(at) % 60:02d} - {span:5.2f} с, {weight / 1e6:6.2f} МБ, "
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
    try:
        found = keyframes(args.url)
    except TorrcastError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        f"взято {found.taken / 1e6:.1f} МБ за {found.requests} запроса, точек {len(found.points)}"
    )
    report(found.duration, found.points, args.grid)


if __name__ == "__main__":
    main()
