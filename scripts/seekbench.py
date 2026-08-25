#!/usr/bin/env python3
"""Цена дальней перемотки со стороны снабжения: приёмника тут нет вовсе.

Отвечает на один вопрос: сколько плёнки наш тракт вообще СПОСОБЕН отдать в первые
секунды после прыжка в непрогретое. Это потолок, а не подражание приёмнику: сегменты
забираются так быстро, как они готовы, и ни один приёмник больше этого не получит.
Отдал тракт за окно меньше самого окна - плёнка потеряна на нашей стороне; отдал
заметно больше - на нашей стороне её терять негде, и искать надо у приёмника.

Слагаемых у прыжка три, и меряются они по отдельности:

* **подъём упаковки** - от команды до ПЕРВОГО готового куска, за вычетом первого байта
  входа: столько стоит поднять ffmpeg и довести его до первого выложенного сегмента;
* **рой** - отдельным прибором: сырой Range-запрос к источнику в тот же байт, куда
  прыгнули, - когда пришёл первый байт и сколько мегабит в секунду он держит дальше.
  Меньше битрейта картины - плёнку теряет рой, и упаковка тут ни при чём;
* **кодировщик** - выпуск плёнки в разах к реальному времени при живом рое: тракт с
  перекодом упирается в процессор, и тогда рой отдаёт с запасом, а плёнка всё равно
  не поспевает.

    python3 scripts/seekbench.py --source "http://127.0.0.1:8090/stream?link=<хеш>&index=1&play" \\
        --to 4200 --window 90

Инструмент разработчика: в устанавливаемый пакет не входит.
"""

from __future__ import annotations

import argparse
import functools
import shutil
import sys
import time
import urllib.request
from dataclasses import replace
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from probeprofile import add_argument as add_profile_argument
from probeprofile import choose as choose_profile
from seekcheck import free_port, get, serve_file, unfit_grid

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.http_server.hls_server import HlsServer
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.hls_dir import hls_dir
from torrcast.adapters.stream_probe.probe import probe
from torrcast.adapters.stream_probe.segment_name import segment_name
from torrcast.runtime.wire import wire
from torrcast.usecases.feed_pack.feed import Feed
from torrcast.usecases.playback.layout import layout


def swarm(url: str, share: float, seconds: float) -> tuple[float, float]:
    """Отдельный прибор для роя: ``(секунд до первого байта, Мбит/с дальше)``.

    Ходит в источник МИМО упаковки - сырым Range-запросом в тот самый байт, куда
    прыгнули. Поэтому его число ни с чем не смешано: ffmpeg тут не участвует, процессор
    свободен, и всё, что видно, - это скорость самой раздачи в холодном месте файла.

    ⚠️ Прибор этот греет рою ровно то место, в которое сейчас прыгнет упаковка, и
    зовётся он ПОСЛЕ замера окна: спрошенный раньше, он подарил бы упаковке чужой
    прогрев и занизил бы её цену.
    """
    # Длина спрашивается Range-запросом, а не ``HEAD``: ``HEAD`` умеют не все источники,
    # а ``Content-Range`` обязан назвать полный размер каждый, кто Range вообще держит.
    probe_one = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
    with urllib.request.urlopen(probe_one, timeout=30.0) as head:
        head.read()
        _, _, total = (head.headers.get("Content-Range") or "").partition("/")
    size = int(total) if total.isdigit() else 0
    if not size:
        return 0.0, 0.0  # длины файла источник не назвал - в какой байт прыгать, неизвестно
    request = urllib.request.Request(url, headers={"Range": f"bytes={int(share * size)}-"})
    began = time.monotonic()
    with urllib.request.urlopen(request, timeout=60.0) as answer:
        first = answer.read(1)
        touched = time.monotonic() - began
        got = len(first)
        while time.monotonic() - began < seconds:
            chunk = answer.read(1 << 16)
            if not chunk:
                break
            got += len(chunk)
    flowed = max(1e-9, time.monotonic() - began - touched)
    return touched, got * 8 / 1e6 / flowed


def leap(feed: Feed, base: str, to: float, window: float, timeout: float) -> dict[str, float]:
    """Прыжок в ``to`` и окно ``window``: сколько плёнки тракт отдал и когда начал.

    Куски забираются подряд и без пауз - меряется потолок отдачи, а не поведение
    приёмника. Ожидание тела тут законное: показ ровно так и ждёт кусок, который ещё
    пакуется (:attr:`Profile.hold_seconds`), и это ожидание и есть искомая цена.
    """
    grid = feed.grid
    slot = grid.slot_at(to)
    began = time.monotonic()
    feed.restart(slot)
    film, first_at, gave = 0.0, 0.0, 0
    while time.monotonic() - began < window and slot < grid.count - 1:
        code, size, waited = get(f"{base}/{segment_name(slot)}", timeout)
        spent = time.monotonic() - began
        if code != 200 or not size:
            print(f"  v{slot:<4} · 🔴 код {code} на {spent:5.1f} с - плёнки не будет")
            break
        if not first_at:
            first_at = spent
        film += grid.span(slot)
        gave += 1
        print(
            f"  v{slot:<4} ({grid.start(slot):7.1f} с) · {size / 1e6:6.2f} МБ · "
            f"ждал {waited:5.1f} с · плёнки {film:6.1f} с за {spent:5.1f} с стенки"
        )
        feed.prune(grid.start(slot))
        slot += 1
    spent = time.monotonic() - began
    return {"film": film, "spent": spent, "first": first_at, "given": float(gave)}


def main() -> int:
    wire()
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source", help="URL потока (TorrServer)")
    source.add_argument("--file", help="локальный файл - поднимем ему Range-раздачу сами")
    parser.add_argument("--to", type=float, required=True, help="куда прыгаем, секунда фильма")
    parser.add_argument("--window", type=float, default=90.0, help="окно замера, с")
    parser.add_argument("--swarm", type=float, default=20.0, help="сколько мерить рой, с")
    parser.add_argument("--out", default="/dev/shm/seekbench", help="каталог показа")
    parser.add_argument("--step", type=float, default=10.0, help="шаг сетки, с")
    parser.add_argument("--keep", type=float, default=120.0, help="окно позади показа, с")
    parser.add_argument("--mbit", type=float, default=9.0, help="во сколько перекодировать")
    parser.add_argument("--whole", action="store_true", help="перекодировать фильм целиком")
    add_profile_argument(parser)
    args = parser.parse_args()

    url = args.source or serve_file(Path(args.file).resolve())
    media = probe(url)
    print(f"источник: {url}\nдлительность {media.duration:.1f} с, видео {media.video}")
    config, choice = choose_profile(load_config(), args.profile)
    config = replace(config, recode=True, recode_mbit=args.mbit, hls_segment=args.step)
    if args.whole:
        # Порог «тяжёл каждый кусок» опущен ниже любого веса: замер меряет ИМЕННО сплошной
        # перекод, но решение о нём всё равно принимает показ, а не замер.
        config = replace(config, bitrate_hard_mbit=-1.0)
    grid, whole = layout(
        config,
        url,
        media.duration,
        media.video or "",
        max(0.0, media.video_bps / 1e6),
        say=print,
        depth=media.depth,
        profile=choice.profile,
        frame=media.frame,
        hdr=media.hdr,
    )
    unfit = unfit_grid(cast(Grid, grid), args.step)
    if unfit:
        print(f"🔴 материал негоден для сеточного замера: {unfit}", file=sys.stderr)
        return 2
    print(
        f"перекод: {'сплошной, ' + whole.preset if whole is not None else 'нет'}; "
        f"сетка {grid.count} кусков; приёмник {choice.profile.title}"
    )

    out = hls_dir(args.out)
    feed = Feed(
        source=url,
        audio=0,
        out=out,
        grid=grid,
        keep=args.keep,
        burst=choice.profile.burst,
        wait=choice.profile.hold_seconds,
        cap=choice.profile.max_segment_bytes,
        log=functools.partial(print, "  упаковка:"),
        encode=whole,
    )
    port = free_port()
    server = HlsServer(out, host="127.0.0.1", port=port, feed=feed)
    server.start()
    base = f"http://127.0.0.1:{port}"
    try:
        print(f"\n- прыжок в {args.to:.0f} с, окно {args.window:.0f} с -")
        got = leap(feed, base, args.to, args.window, choice.profile.hold_seconds + 30.0)
    finally:
        feed.stop()
        server.stop()
        shutil.rmtree(out, ignore_errors=True)

    # Рой спрашивается ПОСЛЕ окна: раньше он прогрел бы место прыжка за счёт замера.
    share = args.to / media.duration if media.duration > 0 else 0.0
    touched, mbit = swarm(url, share, args.swarm)
    need = max(0.0, media.video_bps / 1e6)
    pace = got["film"] / max(1e-9, got["spent"])
    spare = mbit > need
    # Виноватого называет ДЕФИЦИТ, а не запас у соседа: тракт, отдавший плёнки больше
    # стенки, ничего не терял, и подозревать в этом окне некого. Пока строка мерила
    # только полосу роя, она объявляла кодировщик подозреваемым на прогоне 1.61x - то
    # есть там, где терять было нечего.
    blame = (
        "терять нечего: тракт отдал плёнки больше стенки"
        if pace >= 1.0
        else ("кодировщик: рой с запасом, а плёнка не поспевает" if spare else "рой: полосы нет")
    )
    print(
        f"\nитог прыжка в {args.to:.0f} с:\n"
        f"  плёнка за окно      {got['film']:6.1f} с на {got['spent']:.1f} с стенки "
        f"({pace:.2f}x реального времени, {int(got['given'])} кусков)\n"
        f"  первый кусок        {got['first']:6.1f} с\n"
        f"  подъём упаковки     {max(0.0, got['first'] - touched):6.1f} с "
        f"(первый кусок минус первый байт входа)\n"
        f"  рой                 {touched:6.1f} с до первого байта, дальше {mbit:.1f} Мбит/с "
        f"при нужных {need:.1f}\n"
        f"  виноватый окна      {blame}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
