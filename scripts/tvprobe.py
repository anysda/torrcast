"""Короткий смок на живом ТВ: одно место фильма, одна сетка, честная лента состояний.

Отвечает на вопрос «какая именно граница убивает показ». Работает **тем же кодом**,
что и показ (:class:`torrcast.stream.Feed`, :class:`torrcast.cast.ChromecastReceiver`),
меняется ровно одно: сетка сегментов, которую задают снаружи. Поэтому разница в поведении
ТВ — это разница в нарезке, а не в обвязке.

    python3 scripts/tvprobe.py <url> --at 76 --watch 25 --step 4 --uniform
    python3 scripts/tvprobe.py <url> --at 76 --watch 25 --bounds 60,70,80,84,90,100

Печатает ленту «секунда показа → позиция → состояние» и вердикт: где встал, насколько,
был ли запас упаковки в этот момент (то есть ждал ли приёмник нас или завис сам).

⚠️ Состояние показа (``state.json``) не трогает вовсе, чужой показ не перебивает: если на
ТВ уже что-то играет, смок отказывается стартовать.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.cast import ChromecastReceiver
from torrcast.recode import RECODE_DIR, Encode, Recoder, Weights
from torrcast.state import load_config
from torrcast.stream import Feed, Grid, HlsServer, film_keys, grid_for, hls_base, hls_dir, probe

#: Позиция не двигается дольше этого при живом запасе упаковки — это подвис.
STALL = 3.0


def make_grid(args: argparse.Namespace, delivered: float = 0.0) -> Grid:
    """Сетка смока: явный список границ, ровная или по опорным кадрам.

    ``--drop``/``--add`` двигают отдельные границы, не трогая остальную сетку, — это и
    есть бисект: между прогонами меняется ровно одна граница.

    ``delivered`` и потолок перекодирования идут в сетку ровно так же, как в показе
    (:func:`torrcast.cli._play`): от них зависит потолок веса сегмента, а смок обязан
    резать так же, как настоящий показ, иначе он меряет не то.
    """
    if args.bounds:
        given = tuple(float(x) for x in args.bounds.split(","))
        base = Grid((0.0, *given) if given[0] > 0 else given, args.duration, False)
    else:
        base = grid_for(
            args.url,
            args.duration,
            args.step,
            not args.uniform,
            say=print,
            delivered_mbit=delivered,
            ceiling_mbit=args.mbit if args.recode else 0.0,
        )
    drop = {float(x) for x in args.drop.split(",") if x}
    extra = {float(x) for x in args.add.split(",") if x}
    if not drop and not extra:
        return base
    bounds = sorted({b for b in base.bounds if not any(abs(b - d) < 0.001 for d in drop)} | extra)
    print(f"правка сетки: убрано {sorted(drop)}, добавлено {sorted(extra)}")
    return Grid(tuple(bounds), base.duration, base.on_keys)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="поток TorrServer")
    parser.add_argument("--at", type=float, required=True, help="с какой секунды грузить показ")
    parser.add_argument("--watch", type=float, default=25.0, help="сколько секунд смотреть")
    parser.add_argument("--step", type=float, default=10.0)
    parser.add_argument("--uniform", action="store_true", help="ровная сетка, не по кадрам")
    parser.add_argument("--bounds", default="", help="явные границы через запятую")
    parser.add_argument("--drop", default="", help="убрать эти границы из сетки")
    parser.add_argument("--add", default="", help="добавить эти границы в сетку")
    parser.add_argument(
        "--seek", default="", help="перемотки: «секунда_смока:место_фильма» через запятую"
    )
    parser.add_argument("--duration", type=float, default=6500.285, help="длина фильма")
    parser.add_argument("--audio", type=int, default=0)
    parser.add_argument("--title", default="проверка нарезки")
    parser.add_argument("--recode", action="store_true", help="перекодировать тяжёлые куски")
    parser.add_argument("--threshold", type=float, default=15.0, help="порог тяжести, Мбит/с")
    parser.add_argument("--preset", default="veryfast")
    parser.add_argument("--mbit", type=float, default=12.0, help="во сколько перекодировать")
    parser.add_argument("--extra", type=float, default=0.0, help="поправка «контейнер → ТВ»")
    parser.add_argument(
        "--head-wait", type=float, default=12.0, help="ждать перекод первого сегмента, с"
    )
    parser.add_argument(
        "--poll", type=float, default=0.5, help="как часто опрашивать приёмник, с (показ — 2.0)"
    )
    args = parser.parse_args()

    config = load_config()
    out = hls_dir(config.hls_dir)
    media = None if (args.uniform or args.bounds) else probe(args.url)
    delivered = media.delivered_mbit if media else 0.0
    if media is not None:
        print(
            f"паспорт: видео {media.video_bps / 1e6:.2f} Мбит/с, на ТВ уедет {delivered:.2f} Мбит/с"
            if delivered > 0
            else "паспорт веса видеодорожки не несёт — поправка наберётся по факту"
        )
    grid = make_grid(args, delivered)
    slot = grid.slot_at(args.at)
    print(
        f"сетка: {grid.count} сегментов; место {args.at:.1f} с — это v{slot} "
        f"[{grid.start(slot):.3f}..{grid.end(slot):.3f}), соседи: "
        + ", ".join(
            f"{grid.start(k):.3f}" for k in range(max(0, slot - 1), min(grid.count, slot + 4))
        )
    )

    recoder = None
    if args.recode:
        keys = film_keys(args.url)
        # Профиль как в показе: вес видеодорожки из паспорта ffprobe. ``--extra``
        # оставлен ручным перебивом — им же меряется цена ошибки в поправке.
        weights = Weights.of(
            keys, grid, extra=args.extra, delivered=0.0 if args.extra else delivered
        )
        if weights is None:
            print("карта без смещений — профиля тяжести нет")
        else:
            print(
                f"поправка «контейнер → ТВ»: {weights.extra:.2f} Мбит/с "
                f"(контейнер {weights.container:.2f})"
            )
            heavy = weights.heavy(args.threshold)
            near = [s for s in heavy if slot <= s < slot + 20]
            print(f"тяжёлых в фильме {len(heavy)} из {grid.count}; впереди по ходу: {near}")
            recoder = Recoder(
                source=args.url,
                audio=args.audio,
                grid=grid,
                spare=out / RECODE_DIR,
                weights=weights,
                threshold=args.threshold,
                encode=Encode(preset=args.preset, mbit=args.mbit),
                head_wait=args.head_wait,
                log=lambda text: print(f"  кодировщик: {text}", flush=True),
            )
    feed = Feed(
        source=args.url,
        audio=args.audio,
        out=out,
        grid=grid,
        readrate=config.hls_readrate,
        burst=config.hls_burst,
        keep=config.hls_keep,
        log=lambda text: print(f"  упаковка: {text}", flush=True),
        recoder=recoder,
    )
    server = HlsServer(out, port=config.hls_port, feed=feed)
    receiver = ChromecastReceiver(config.tv or "")
    url = f"{hls_base(config)}/index.m3u8"

    lowest, stalls, buffering = args.at, [], 0
    try:
        server.start()
        if recoder is not None:
            recoder.played = args.at
            recoder.start()
        feed.restart(slot)
        began = time.monotonic()
        receiver.play(url, args.title, at=args.at)
        print(f"картинка через {time.monotonic() - began:.1f} с, смотрю {args.watch:.0f} с")
        watch_from = time.monotonic()
        seen, since, worst = -1.0, 0.0, 0.0
        jumps = [(float(a), float(b)) for a, b in (p.split(":") for p in args.seek.split(",") if p)]
        while time.monotonic() - watch_from < args.watch:
            if jumps and time.monotonic() - watch_from >= jumps[0][0]:
                where = jumps.pop(0)[1]
                print(f"  перемотка на {where:.1f} с", flush=True)
                receiver._device().media_controller.seek(where)  # щуп лезет напрямую
            position = receiver.position(feed.front(seen if seen > 0 else args.at))
            now = time.monotonic() - watch_from
            front = feed.front(position.pos)
            print(
                f"  {now:5.1f} с · позиция {position.pos:8.3f} · упаковано {front:8.3f} "
                f"· запас {front - position.pos:6.1f} · {position.state}",
                flush=True,
            )
            if position.state == "BUFFERING":
                buffering += 1
            if recoder is not None:
                recoder.played = position.pos
            if abs(position.pos - seen) < 0.05:
                if now - since > STALL and front - position.pos > 1.0:
                    worst = max(worst, now - since)
                    stalls.append((position.pos, now - since))
            else:
                seen, since = position.pos, now
            lowest = max(lowest, position.pos)
            time.sleep(args.poll)
    finally:
        with contextlib.suppress(Exception):
            receiver.stop()
        feed.stop()
        server.stop()

    print(f"опросов в BUFFERING за прогон: {buffering}")
    if recoder is not None:
        print(f"кодировщик: {recoder.report()}")
    if stalls:
        where = max(stalls, key=lambda s: s[1])
        print(
            f"ВЕРДИКТ: встал на {where[0]:.3f} с (сегмент v{grid.slot_at(where[0])}), "
            f"держался {where[1]:.1f} с при живом запасе"
        )
    else:
        print(f"ВЕРДИКТ: чисто, дошёл до {lowest:.3f} с без подвисов")


if __name__ == "__main__":
    main()
