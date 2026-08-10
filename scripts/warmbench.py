"""Синтетический замер голодания прогрева: приёмник не трогается вовсе.

Вместо телевизора - ПОДДЕЛЬНЫЙ читатель темпа: он держит запас живого показа около
GUARD_LOW обратной связью (прогрев активен -> запас проседает; прогрев замер -> запас
восстанавливается, но упирается в потолок ниже GUARD_HIGH, потому что показ идёт вплотную
за упаковкой). Настоящий ffmpeg греет настоящий ролик во временный каталог - боевое
хранилище не трогается (TORRCAST_WARM).

Мерим ДВУМЯ способами:
  1. событие: сколько прогрев простоял под SIGSTOP и когда наступило "прогрета целиком";
  2. независимо: расхождение прогретого объёма (секунд фильма на диске) со стеной времени -
     самый долгий "плоский" участок, где стена идёт, а прогретое стоит.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.stream import Grid
from torrcast.warm import GUARD_HIGH, GUARD_LOW, Vault, Warmer


class TempoReader:
    """Подделка темпа потребления: гонит запас показа обратной связью по idle прогрева.

    ``ceiling`` - потолок запаса, когда прогрев замер (показ вплотную за упаковкой не даёт
    упаковке уйти дальше). ``floor`` - куда валится запас, пока прогрев активно тянет из той
    же раздачи. Оба параметра - это и есть "здоровый, но тесный показ" против "реально
    просевшего".
    """

    def __init__(self, warmer: Warmer, floor: float, ceiling: float, warm_start: float = 55.0):
        self.warmer = warmer
        self.floor = floor
        self.ceiling = ceiling
        self.slack = warm_start  # даём прогреву стартовать (нужен запас > GUARD_HIGH)
        self.stop = False
        self.samples: list[tuple[float, float, float, bool]] = []  # t, slack, warmed, idle

    def run(self) -> None:
        began = time.monotonic()
        # первые 3 с - показ здоров, прогрев трогается с места
        while time.monotonic() - began < 3.0 and not self.stop:
            self.warmer.feed(self.slack)
            self.samples.append(
                (time.monotonic() - began, self.slack, self.warmer.warmed, self.warmer.idle)
            )
            time.sleep(0.25)
        # дальше - тесный режим: цель зависит от того, тянет прогрев или замер
        while not self.stop:
            target = self.ceiling if self.warmer.idle else self.floor
            # линейное приближение к цели, шаг соразмерен реальной динамике буфера
            step = 6.0 * 0.25  # ~6 с запаса в секунду
            if self.slack < target:
                self.slack = min(target, self.slack + step)
            else:
                self.slack = max(target, self.slack - step)
            self.warmer.feed(self.slack)
            self.samples.append(
                (time.monotonic() - began, self.slack, self.warmer.warmed, self.warmer.idle)
            )
            time.sleep(0.25)


def measure(
    clip: str, floor: float, ceiling: float, rate: float, wall: float, warm_dir: Path
) -> dict[str, Any]:
    grid = Grid.uniform(_duration(clip))
    vault = Vault(root=warm_dir, key="bench", budget=1 << 34, floor=0)
    warmer = Warmer(source=clip, audio=0, grid=grid, vault=vault, rate=rate)
    reader = TempoReader(warmer, floor=floor, ceiling=ceiling)
    thread = threading.Thread(target=reader.run, daemon=True)

    warmer.start()
    thread.start()
    began = time.monotonic()
    done_at = None
    while time.monotonic() - began < wall:
        if warmer.done:
            done_at = time.monotonic() - began
            break
        time.sleep(0.2)
    reader.stop = True
    warmer.stop()
    thread.join(timeout=2.0)

    # способ 1: доля времени под SIGSTOP
    idle_time = sum(0.25 for _, _, _, idle in reader.samples if idle)
    span = reader.samples[-1][0] if reader.samples else 0.0
    # способ 2: самый долгий плоский участок прогретого (стена идёт, прогрето стоит)
    longest_flat, flat_start, last_warmed = 0.0, None, -1.0
    for t, _slk, warmed, _idle in reader.samples:
        if warmed <= last_warmed + 1e-6:
            if flat_start is None:
                flat_start = t
            longest_flat = max(longest_flat, t - flat_start)
        else:
            flat_start = None
            last_warmed = warmed
    final_warmed = reader.samples[-1][2] if reader.samples else 0.0
    return {
        "grid_count": grid.count,
        "duration": grid.duration,
        "done": warmer.done,
        "done_at": done_at,
        "warmed_final": final_warmed,
        "wall": span,
        "idle_time": idle_time,
        "idle_frac": idle_time / span if span else 0.0,
        "longest_flat": longest_flat,
        "breaks": warmer.breaks,
    }


def _duration(clip: str) -> float:
    import subprocess

    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            clip,
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return float(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--rate", type=float, default=4.0)
    ap.add_argument("--wall", type=float, default=90.0)
    ap.add_argument("--floor", type=float, default=15.0, help="куда валится запас под прогревом")
    ap.add_argument("--ceiling", type=float, default=35.0, help="потолок запаса, прогрев замер")
    ap.add_argument("--warm-dir", default=str(Path(tempfile.gettempdir()) / "torrcast-warmbench"))
    args = ap.parse_args()

    warm_dir = Path(args.warm_dir)
    os.environ["TORRCAST_WARM"] = str(warm_dir)
    import shutil

    shutil.rmtree(warm_dir, ignore_errors=True)

    print(f"GUARD_LOW={GUARD_LOW}  GUARD_HIGH={GUARD_HIGH}  rate={args.rate}")
    print(f"сценарий: floor={args.floor} ceiling={args.ceiling} (запас держится в этой полосе)")
    r = measure(args.clip, args.floor, args.ceiling, args.rate, args.wall, warm_dir)
    print(f"  сегментов: {r['grid_count']}  длительность фильма: {r['duration']:.0f} с")
    done = f" на {r['done_at']:.1f} с стены" if r["done_at"] else " (НЕ достигнуто за окно)"
    print(f"  прогрета целиком: {r['done']}{done}")
    print(f"  прогрето итого: {r['warmed_final']:.0f} из {r['duration']:.0f} с фильма")
    print(f"  стена: {r['wall']:.1f} с")
    print(f"  [способ 1] под SIGSTOP: {r['idle_time']:.1f} с ({100 * r['idle_frac']:.0f}% времени)")
    print(f"  [способ 2] самый долгий застой прогретого: {r['longest_flat']:.1f} с")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
