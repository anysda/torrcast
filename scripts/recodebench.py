#!/usr/bin/env python3
"""Замеры под динамический битрейт: скорость кодека и профиль тяжести фильма.

Три режима, и все три отвечают на вопросы, от которых зависит сама возможность затеи:

``--speed ФАЙЛ``
    Сколько реального времени стоит секунда 1080p на этой машине — по каждому пресету
    libx264. Вход берётся готовым куском фильма (см. ``--dump``), чтобы рой и сеть в
    замер не лезли. Пример замера на 4 vCPU (Xeon E5-2696 v4, вход 23.7 Мбит/с, кап 12/13):
    ultrafast 4.36×, superfast 2.62×, veryfast 1.54×, faster 1.04×, fast 0.72×, medium 0.55×.

``--profile ХЕШ``
    Профиль тяжести фильма по карте опорных кадров: сколько сегментов сетки приёмник не
    потянет, где они стоят и какими сериями идут. Ни одного упакованного сегмента для
    этого не нужно — всё считается из карты.

``--plan ХЕШ --at СКОРОСТЬ``
    Модель показа: успевает ли кодировщик, работая с нулевой секунды и по порядку фильма.
    Отвечает на единственный вопрос, который решает архитектуру, — сколько тяжёлых кусков
    доедет до показа неготовыми.

⚠️ Замер скорости не переносится на машину с другим числом ядер: числа в
:data:`torrcast.recode.PRESETS` сняты на одной машине и на такой же должны пересниматься.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.recode import Encode, Weights
from torrcast.search import magnet_for
from torrcast.state import load_config
from torrcast.stream import (
    Grid,
    Packer,
    TorrServer,
    ffmpeg_pack_command,
    film_keys,
    grid_for,
    pick_video_file,
    segment_slot,
)

PRESET_LADDER = ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium")


def _film(torrent_hash: str) -> tuple[str, int]:
    """Поднять раздачу и вернуть URL файла видео и его размер."""
    config = load_config()
    torrserver = TorrServer(config.torrserver_url)
    key = torrserver.add(magnet_for(torrent_hash))
    found = pick_video_file(torrserver.wait_files(key, timeout=180.0))
    return torrserver.stream_url(key, found.index), found.size


def _grid_of(url: str, step: float) -> tuple[Grid, object]:
    keys = film_keys(url)
    grid = grid_for(url, keys.duration, step, True, say=lambda t: print(f"  {t}"))
    return grid, keys


def speed(path: Path) -> None:
    """Таблица «пресет → во сколько раз быстрее реального времени»."""
    duration = float(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout.strip().split(",")[0]
    )  # fmt: skip
    size = path.stat().st_size
    print(f"вход: {duration:.2f} с, {size / 2**20:.1f} МБ, {size * 8 / duration / 1e6:.2f} Мбит/с")
    print(f"\n{'пресет':<11}{'wall, с':>9}{'xRT':>8}{'Мбит/с':>10}")
    out = path.with_name("bench-out.ts")
    for preset in PRESET_LADDER:
        encode = Encode(preset=preset, mbit=12.0)
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
            "-map", "0:v:0", "-map", "0:a:0",
            # Принудительные опорные кадры тут ни при чём: меряем чистую скорость кодека.
            *[a for a in encode.args(Grid((0.0,), duration), 0, 0)
              if a != "-force_key_frames"][:-1],
            "-g", "250", "-c:a", "copy", "-f", "mpegts", str(out),
        ]  # fmt: skip
        began = time.monotonic()
        subprocess.run(command, capture_output=True, check=True)
        spent = time.monotonic() - began
        got = out.stat().st_size
        print(
            f"{preset:<11}{spent:>9.1f}{duration / spent:>7.2f}x{got * 8 / duration / 1e6:>10.2f}"
        )
        out.unlink(missing_ok=True)


def profile(torrent_hash: str, step: float, threshold: float, extra: float) -> None:
    """Профиль тяжести фильма по карте опорных кадров."""
    url, size = _film(torrent_hash)
    print(f"файл: {url}\nразмер: {size / 2**30:.2f} ГиБ")
    grid, keys = _grid_of(url, step)
    weights = Weights.of(keys, grid, extra=extra)  # type: ignore[arg-type]
    if weights is None:
        print("карта без смещений — профиля не будет")
        return
    total = grid.duration
    print(f"\nпоправка «контейнер → ТВ»: {extra:.2f} Мбит/с (замерь --calibrate)")
    mean = sum(weights.at(s) * grid.span(s) for s in range(grid.count)) / total
    print(f"средний доставляемый: {mean:.2f} Мбит/с")
    for level in (12, 14, 15, 16, 18, 20):
        heavy = weights.heavy(float(level))
        seconds = sum(grid.span(s) for s in heavy)
        print(
            f"  >= {level:2} Мбит/с: {len(heavy):4} сегм. из {grid.count} "
            f"({seconds:5.0f} с, {100 * seconds / total:4.1f}% фильма)"
        )
    heavy = set(weights.heavy(threshold))
    runs, cur = [], None
    for slot in range(grid.count):
        if slot in heavy:
            cur = [slot, slot] if cur is None else [cur[0], slot]
        elif cur:
            runs.append(tuple(cur))
            cur = None
    if cur:
        runs.append(tuple(cur))
    print(
        f"\nпри пороге {threshold:.0f}: серий подряд идущих тяжёлых {len(runs)}, "
        f"самая длинная {max((b - a + 1) for a, b in runs) if runs else 0} сегм."
    )
    print("топ-10 тяжёлых:")
    for slot in sorted(range(grid.count), key=lambda s: -weights.at(s))[:10]:
        print(
            f"  v{slot:<4} {grid.start(slot) / 60:6.2f} мин  span={grid.span(slot):5.2f} с  "
            f"{weights.at(slot):6.2f} Мбит/с"
        )


def plan(
    torrent_hash: str, step: float, threshold: float, extra: float, rate: float, horizon: float
) -> None:
    """Модель показа: успевает ли кодировщик при скорости ``rate`` (× реального времени)."""
    url, _ = _film(torrent_hash)
    grid, keys = _grid_of(url, step)
    weights = Weights.of(keys, grid, extra=extra)  # type: ignore[arg-type]
    assert weights is not None
    pending = list(weights.heavy(threshold))
    busy, late, worst, work = 0.0, 0, 0.0, 0.0
    while pending:
        ready = [s for s in pending if grid.start(s) <= busy + horizon]
        if not ready:
            busy = min(grid.start(s) for s in pending) - horizon
            continue
        slot = min(ready)
        pending.remove(slot)
        busy += grid.span(slot) / rate
        work += grid.span(slot) / rate
        if busy > grid.start(slot):
            late += 1
            worst = max(worst, busy - grid.start(slot))
    heavy = weights.heavy(threshold)
    print(f"скорость {rate:.2f}xRT, горизонт {horizon:.0f} с, порог {threshold:.0f} Мбит/с:")
    print(
        f"  тяжёлых {len(heavy)}, опоздали {late}, худшее опоздание {worst:.0f} с, "
        f"работы кодировщику {work / 60:.1f} мин на фильм {grid.duration / 60:.0f} мин"
    )


def dump(torrent_hash: str, step: float, slot: int, count: int, where: Path) -> None:
    """Выложить несколько настоящих сегментов фильма на диск — вход для ``--speed``."""
    url, _ = _film(torrent_hash)
    grid, _ = _grid_of(url, step)
    shutil.rmtree(where, ignore_errors=True)
    (where / "run").mkdir(parents=True)
    from torrcast.stream import pack_start

    at = pack_start(url, grid.start(slot))
    command = ffmpeg_pack_command(url, 0, str(where / "run"), grid, slot, at, readrate=0.0)
    packer = Packer.start(command, where, where / "run", slot)
    began = time.monotonic()
    while time.monotonic() - began < 900:
        packer.publish()
        if packer.edge >= slot + count - 1 or packer.poll() is not None:
            break
        time.sleep(0.5)
    packer.stop(keep_files=True, reason="хватит")
    made = sorted(where.glob("v*.ts"), key=lambda p: segment_slot(p.name))[:count]
    joined = where / "in.ts"
    with joined.open("wb") as sink:
        for piece in made:
            sink.write(piece.read_bytes())
    print(f"сложено {len(made)} сегментов в {joined} ({joined.stat().st_size / 2**20:.1f} МБ)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speed", type=Path, help="замер скорости пресетов на готовом куске")
    parser.add_argument("--profile", help="профиль тяжести раздачи (хеш)")
    parser.add_argument("--plan", help="модель показа для раздачи (хеш)")
    parser.add_argument("--dump", help="выложить сегменты раздачи на диск (хеш)")
    parser.add_argument("--slot", type=int, default=0)
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--where", type=Path, default=Path("/root/bench/seg"))
    parser.add_argument("--step", type=float, default=10.0)
    parser.add_argument("--threshold", type=float, default=15.0)
    parser.add_argument("--extra", type=float, default=0.0, help="поправка «контейнер → ТВ»")
    parser.add_argument("--at", type=float, default=1.4, help="скорость кодировщика, xRT")
    parser.add_argument("--horizon", type=float, default=300.0)
    parser.add_argument("--json", type=Path, help="куда сложить профиль машиночитаемо")
    args = parser.parse_args()
    if args.speed:
        speed(args.speed)
    elif args.profile:
        profile(args.profile, args.step, args.threshold, args.extra)
    elif args.plan:
        plan(args.plan, args.step, args.threshold, args.extra, args.at, args.horizon)
    elif args.dump:
        dump(args.dump, args.step, args.slot, args.count, args.where)
    else:
        parser.print_help()
    if args.json:
        args.json.write_text(json.dumps({"сделано": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
