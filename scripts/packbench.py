#!/usr/bin/env python3
"""Замер несданных кусков: сколько упаковка держит в tmpfs, пока их никто не забирает.

Приёмника тут нет вовсе. Поднимается живая упаковка, у неё берут первый кусок - и больше
не берут ничего: ровно так выглядит показ, который читает прогретое с диска. Мерятся два
числа рядом - окно показа (то, что выложено наружу) и несданное каталога прогона.

    python scripts/packbench.py --clip clip.mkv --seconds 720 --rate 8 --watch 90
    python scripts/packbench.py --clip clip.mkv --seconds 720 --rate 8 --watch 90 --sweep

Инструмент разработчика: в устанавливаемый пакет не входит.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.hls_dir import hls_dir
from torrcast.adapters.stream_pack.packer import Packer
from torrcast.runtime.wire import wire
from torrcast.usecases.feed_pack.feed import Feed


def main() -> int:
    # Медиатракт сценарию раздаёт композиционный корень: без него лента показа не
    # знает ни имён сегментов, ни чем паковать.
    wire()
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", required=True, help="файл, который пакуем")
    ap.add_argument("--seconds", type=float, required=True, help="длительность файла")
    ap.add_argument("--rate", type=float, default=1.0, help="темп чтения (-readrate)")
    ap.add_argument("--watch", type=float, default=60.0, help="сколько секунд смотрим")
    ap.add_argument("--dir", default="/dev/shm/packbench", help="каталог показа (tmpfs)")
    ap.add_argument("--sweep", action="store_true", help="звать выкладку по часам показа")
    ap.add_argument("--prune", action="store_true", help="убирать пройденное, как это делает показ")
    ap.add_argument("--cap", type=int, default=0, help="потолок несданного, байты")
    ap.add_argument("--stuck", action="store_true", help="выкладка встала: держим каждый кусок")
    args = ap.parse_args()

    out = hls_dir(args.dir)
    grid = Grid.uniform(args.seconds)
    feed = Feed(
        source=args.clip,
        audio=0,
        out=out,
        grid=grid,
        readrate=args.rate,
        burst=0.0,
        log=lambda text: print(f"    показ: {text}", flush=True),
    )
    if args.cap:
        feed.pending_cap = args.cap
    print(
        f"сетка: {grid.count} кусков по {grid.span(0):.1f} с, темп x{args.rate:g}, "
        f"выкладка по часам: {args.sweep}"
    )
    feed.segment(0)  # единственное обращение к упаковке за весь замер
    if args.stuck and feed.packer is not None:
        # ``hold`` - поле самого прогона, а не договор ленты: щуп берёт его у класса
        # медиатракта, потому что подпирает им ровно выкладку.
        cast(Packer, feed.packer).hold = lambda slot, size=0: True  # нечего отдать
    began = time.monotonic()
    print("секунд_фильма  несдано_МБ  окно_МБ  край")
    try:
        while time.monotonic() - began < args.watch:
            time.sleep(5.0)
            played = (time.monotonic() - began) * args.rate
            if args.sweep:
                feed.sweep()
            if args.prune:
                feed.prune(played)
            packer = feed.packer
            pending = 0 if packer is None else packer.pending()
            window = sum(path.stat().st_size for path in out.glob("v*.ts"))
            edge = -1 if packer is None else packer.edge
            print(
                f"{(time.monotonic() - began) * args.rate:13.0f}  {pending / 1e6:10.1f}  "
                f"{window / 1e6:7.1f}  {edge:4d}",
                flush=True,
            )
    finally:
        feed.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
