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
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from probeprofile import add_argument as add_profile_argument
from probeprofile import choose as choose_profile

from torrcast.cast import ChromecastReceiver
from torrcast.profile import Profile
from torrcast.recode import RECODE_DIR, Encode, Recoder, Weights, whole_encode
from torrcast.runtime.wire import wire
from torrcast.state import load_config
from torrcast.stream import (
    AUDIO_MBIT,
    TS_OVERHEAD,
    Feed,
    Grid,
    HlsServer,
    film_keys,
    grid_for,
    hls_base,
    hls_dir,
    probe,
    segment_name,
)
from torrcast.stream_pack import pack_origin

#: Позиция не двигается дольше этого при живом запасе упаковки - это подвис.
STALL = 3.0

#: Как часто подкладывать ядовитый кусок на место здорового (:func:`spoil`).
POISON_STEP = 0.1

#: Насколько указатель обязан уйти от места захода, чтобы считать это КАДРОМ.
#:
#: 🔴 Замер на живом Q70D: приёмник отвечает ``PLAYING``, ещё ничего не показав, и держит
#: указатель на месте захода, пока не накопит около десяти секунд фильма
#: (:attr:`torrcast.profile.Profile.start_buffer`). Щуп, печатавший «картинку» по слову
#: приёмника, занижал старт на 0-6 с - шесть прогонов подряд, и эти числа успели разойтись
#: по отчётам. Порог взят с запасом от одного кадра (41.7 мс у 23.976 к/с) и от шага опроса.
PICTURE_STEP = 0.4


def shown(pos: float, at: float) -> bool:
    """Есть ли КАДР на экране: указатель ушёл от места захода дальше :data:`PICTURE_STEP`.

    ⚠️ Состояние приёмника тут не спрашивается нарочно: ``PLAYING`` со стоящим указателем
    картинкой не является, а ``BUFFERING`` с едущим - как раз является.
    """
    return pos >= at + PICTURE_STEP


def brew_poison(url: str, grid: Grid, slot: int, audio: int, where: Path) -> Path:
    """Сварить кусок, который приёмник ЗАВЕДОМО не покажет: то же место, но ``yuv444p``.

    Ядовитость тут не догадка, а замер: ``yuv444p`` валит Samsung Q70D целиком - показ
    на таком куске не начинается вовсе. Годится ровно этим: отказ повторяется каждый раз
    и не зависит ни от битрейта, ни от веса, то есть проверяет ВОССТАНОВЛЕНИЕ, а не
    терпение приёмника.
    """
    out = where / f"poison-v{slot}.ts"
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{grid.start(slot):.3f}", "-to", f"{grid.end(slot):.3f}", "-i", url,
        "-map", "0:v:0", "-map", f"0:a:{audio}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv444p",
        "-c:a", "aac", "-ac", "2", "-f", "mpegts", str(out),
    ]  # fmt: skip
    subprocess.run(command, check=True)
    return out


def spoil(ready: Path, target: Path, stop: threading.Event) -> None:
    """Держать ``target`` ядовитым весь показ: упаковка кладёт туда здоровый кусок."""
    while not stop.is_set():
        with contextlib.suppress(OSError):
            if not target.exists() or target.stat().st_size != ready.stat().st_size:
                shutil.copy2(ready, target)
        stop.wait(POISON_STEP)


def make_grid(
    args: argparse.Namespace,
    profile: Profile,
    delivered: float = 0.0,
    whole: Encode | None = None,
) -> Grid:
    """Сетка смока: явный список границ, ровная или по опорным кадрам.

    ``--drop``/``--add`` двигают отдельные границы, не трогая остальную сетку, — это и
    есть бисект: между прогонами меняется ровно одна граница.

    ``delivered`` и потолок перекодирования идут в сетку ровно так же, как в показе
    (:func:`torrcast.cli._play`): от них зависит потолок веса сегмента, а смок обязан
    резать так же, как настоящий показ, иначе он меряет не то.

    ``--ceiling`` отвязывает потолок сетки от цели перекода. Без него два прогона с
    разной целью режут фильм по разным границам, и сравнивать в них нечего: «тот же
    слот» в них - разные куски фильма.
    """
    if args.bounds:
        given = tuple(float(x) for x in args.bounds.split(","))
        base = Grid(
            (0.0, *given) if given[0] > 0 else given,
            args.duration,
            False,
            origin=pack_origin(args.url),
        )
    else:
        base = grid_for(
            args.url,
            args.duration,
            args.step,
            not args.uniform,
            say=print,
            delivered_mbit=delivered,
            ceiling_mbit=(args.ceiling or args.mbit) if args.recode else 0.0,
            # Сплошной перекод: вес куска задаём мы сами, карта источника тут не судья.
            fixed_mbit=(whole.mbit + AUDIO_MBIT) * TS_OVERHEAD if whole is not None else 0.0,
            cap=profile.max_segment_bytes,
        )
    drop = {float(x) for x in args.drop.split(",") if x}
    extra = {float(x) for x in args.add.split(",") if x}
    if not drop and not extra:
        return base
    bounds = sorted({b for b in base.bounds if not any(abs(b - d) < 0.001 for d in drop)} | extra)
    print(f"правка сетки: убрано {sorted(drop)}, добавлено {sorted(extra)}")
    return Grid(tuple(bounds), base.duration, base.on_keys, base.weigh, base.origin)


def main() -> None:
    # Медиатракт сценарию раздаёт композиционный корень: без него лента показа не
    # знает ни имён сегментов, ни чем паковать.
    wire()
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
    parser.add_argument("--whole", action="store_true", help="перекодировать фильм целиком")
    parser.add_argument("--tonemap", action="store_true", help="привести HDR к SDR")
    parser.add_argument("--threshold", type=float, default=15.0, help="порог тяжести, Мбит/с")
    parser.add_argument("--preset", default="veryfast")
    parser.add_argument("--mbit", type=float, default=12.0, help="во сколько перекодировать")
    add_profile_argument(parser)
    parser.add_argument(
        "--ceiling",
        type=float,
        default=0.0,
        help="потолок веса куска для сетки, Мбит/с; 0 - брать --mbit",
    )
    parser.add_argument("--extra", type=float, default=0.0, help="поправка «контейнер → ТВ»")
    parser.add_argument(
        "--head-wait", type=float, default=12.0, help="ждать перекод первого сегмента, с"
    )
    parser.add_argument(
        "--poll", type=float, default=0.5, help="как часто опрашивать приёмник, с (показ - 2.0)"
    )
    parser.add_argument(
        "--poison", type=int, default=-1, help="сделать этот сегмент невоспроизводимым"
    )
    args = parser.parse_args()

    config, choice = choose_profile(load_config(), args.profile)
    out = hls_dir(config.hls_dir)
    # ⚠️ Паспорт нужен и на явной сетке, если перекодируем целиком: из него берутся кадр,
    # HDR и вес видеодорожки, а без них ``--whole`` молча выродился бы в копию - и щуп
    # отдал бы приёмнику ровно тот поток, ради отказа от которого перекод и заведён.
    quiet = (args.uniform or args.bounds) and not args.whole
    media = None if quiet else probe(args.url)
    delivered = media.delivered_mbit if media else 0.0
    if media is not None:
        print(
            f"паспорт: видео {media.video_bps / 1e6:.2f} Мбит/с, на ТВ уедет {delivered:.2f} Мбит/с"
            if delivered > 0
            else "паспорт веса видеодорожки не несёт - поправка наберётся по факту"
        )
    whole = None
    if args.whole and media is not None:
        whole = whole_encode(
            args.mbit,
            video_mbit=media.video_bps / 1e6,
            frame=media.frame,
            ceiling=choice.profile.recode_frame,
            hdr=media.hdr and args.tonemap,
        )
        print(
            f"сплошной перекод: {whole.preset}, {whole.mbit:.2f} Мбит/с, "
            f"кадр {whole.out_frame}, тонемап {whole.hdr}"
        )
    grid = make_grid(args, choice.profile, delivered, whole)
    slot = grid.slot_at(args.at)
    print(
        f"сетка: {grid.count} сегментов; место {args.at:.1f} с - это v{slot} "
        f"[{grid.start(slot):.3f}..{grid.end(slot):.3f}), соседи: "
        + ", ".join(
            f"{grid.start(k):.3f}" for k in range(max(0, slot - 1), min(grid.count, slot + 4))
        )
    )

    recoder = None
    if args.recode:
        keys = film_keys(args.url)
        # Профиль как в показе: вес видеодорожки из паспорта ffprobe. ``--extra``
        # оставлен ручным перебивом - им же меряется цена ошибки в поправке.
        weights = Weights.of(
            keys, grid, extra=args.extra, delivered=0.0 if args.extra else delivered
        )
        if weights is None:
            print("карта без смещений - профиля тяжести нет")
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
        encode=whole,
    )
    server = HlsServer(out, port=config.hls_port, feed=feed)
    receiver = ChromecastReceiver(config.tv or "", profile=choice.profile)
    # Сторож подвиса меряет прыжок сеткой, а не абсолютной секундой: без этого он
    # приземляется в тот же кусок, на котором приёмник и споткнулся.
    receiver.next_cut = grid.after
    url = f"{hls_base(config)}/index.m3u8"

    stop_poison = threading.Event()
    poisoner = None
    if args.poison >= 0:
        ready = brew_poison(args.url, grid, args.poison, args.audio, out.parent)
        target = out / segment_name(args.poison)
        print(
            f"ядовитый v{args.poison} [{grid.start(args.poison):.3f}.."
            f"{grid.end(args.poison):.3f}): {ready.stat().st_size / 1e6:.2f} МБ yuv444p"
        )
        poisoner = threading.Thread(
            target=spoil, args=(ready, target, stop_poison), daemon=True, name="poison"
        )
        poisoner.start()

    lowest, stalls, buffering = args.at, [], 0
    picture: float | None = None
    try:
        server.start()
        if recoder is not None:
            recoder.played = args.at
            recoder.start()
        feed.restart(slot)
        began = time.monotonic()
        receiver.play(url, args.title, at=args.at)
        word = time.monotonic() - began
        print(f"приёмник сказал «играю» через {word:.1f} с (кадра это ещё не значит)")
        print(f"смотрю {args.watch:.0f} с")
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
            if picture is None and shown(position.pos, args.at):
                picture = time.monotonic() - began
                print(
                    f"  КАРТИНКА через {picture:.1f} с "
                    f"(слово опередило её на {picture - word:.1f} с)"
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
        stop_poison.set()
        if poisoner is not None:
            poisoner.join(timeout=2)
        with contextlib.suppress(Exception):
            receiver.stop()
        feed.stop()
        server.stop()

    print(f"опросов в BUFFERING за прогон: {buffering}")
    print(
        f"старт до КАДРА: {picture:.1f} с"
        if picture is not None
        else "старт до КАДРА: указатель так и не сошёл с места захода - картинки не было"
    )
    if recoder is not None:
        print(f"кодировщик: {recoder.report()}")
    if stalls:
        # Отдельное имя: `where` выше держит точку перемотки (float), а тут пара
        # «позиция, длительность»: под одним именем типы не сходятся.
        stall = max(stalls, key=lambda s: s[1])
        print(
            f"ВЕРДИКТ: встал на {stall[0]:.3f} с (сегмент v{grid.slot_at(stall[0])}), "
            f"держался {stall[1]:.1f} с при живом запасе"
        )
    else:
        print(f"ВЕРДИКТ: чисто, дошёл до {lowest:.3f} с без подвисов")


if __name__ == "__main__":
    main()
