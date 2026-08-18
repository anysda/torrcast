"""Доказательство детерминированности нарезки: одни и те же байты при любом старте.

Пакует один и тот же кусок фильма несколькими прогонами, начатыми с разных мест, и
сравнивает результат по трём меркам:

* **границы** — что ffmpeg написал в свой список (``имя,начало,конец``) против того,
  что показ обещал в манифесте (``EXTINF``);
* **байты видео** — md5 элементарного потока H.264 из сегмента. Метки времени в него не
  входят намеренно: у прогона от нуля они на кадр больше (ffmpeg не пускает dts ниже
  нуля), а кадры обязаны быть теми же самыми;
* **длительность** — фактическая против манифестной.

    python3 scripts/gridcheck.py "http://127.0.0.1:8090/stream?link=<hash>&index=1&play" \
        --slots 0,5,7 --upto 150
    python3 scripts/gridcheck.py <url> --step 4 --uniform --slots 0,15 --upto 120
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.grid_for import grid_for
from torrcast.adapters.stream_pack.pack_start import pack_start
from torrcast.usecases.feed_pack.packer import Packer

WORK = Path("/dev/shm/torrcast-gridcheck")


def video_md5(path: Path) -> tuple[str, int]:
    """Хэш байтов видео из сегмента: только кадры, без меток времени и звука."""
    done = subprocess.run(
        ["ffmpeg", "-v", "quiet", "-i", str(path), "-map", "0:v", "-c", "copy", "-f", "h264", "-"],
        capture_output=True,
        check=False,
    )
    return hashlib.md5(done.stdout).hexdigest()[:12], len(done.stdout)


def pack(url: str, grid: Grid, slot: int, upto: int, audio: int) -> tuple[Path, Packer]:
    """Один прогон упаковки от сегмента ``slot`` до сегмента ``upto``."""
    out = WORK / f"start{slot}"
    shutil.rmtree(out, ignore_errors=True)
    (out / "pack").mkdir(parents=True)
    began = time.monotonic()
    at = pack_start(url, grid.start(slot))
    command = ffmpeg_pack_command(url, audio, str(out / "pack"), grid, slot, at, readrate=0.0)
    packer = Packer.start(command, out, out / "pack", slot, grid=grid)
    while packer.frontier() < upto and packer.poll() is None:
        time.sleep(0.5)
    packer.stop(keep_files=True)
    print(
        f"  прогон со слота {slot}: старт ffmpeg на {at:.3f} с "
        f"(докатка {grid.start(slot) - at:.3f} с), {time.monotonic() - began:.1f} с"
    )
    return out, packer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--step", type=float, default=10.0)
    parser.add_argument("--uniform", action="store_true", help="ровная сетка, не по кадрам")
    parser.add_argument("--slots", default="0,5,7", help="с каких сегментов начинать прогоны")
    parser.add_argument("--upto", type=int, default=12, help="до какого сегмента паковать")
    parser.add_argument("--audio", type=int, default=0)
    args = parser.parse_args()

    grid = grid_for(args.url, 0.0, args.step, not args.uniform, say=print)
    starts = [int(s) for s in args.slots.split(",")]
    print(f"сетка: {grid.count} сегментов, фильм {grid.duration:.1f} с")
    print("границы:", ", ".join(f"{grid.start(k):.3f}" for k in range(starts[0], args.upto + 1)))

    runs = {slot: pack(args.url, grid, slot, args.upto, args.audio) for slot in starts}
    print("\nчто нарезал ffmpeg против манифеста:")
    worst = 0.0
    for slot, (_, packer) in runs.items():
        for cut, began, ended in packer.cuts()[1:]:
            if cut < slot or cut > args.upto:
                continue
            span, want = ended - began, grid.span(cut)
            worst = max(worst, abs(began - grid.start(cut)))
            print(
                f"  со слота {slot}: v{cut} {began:9.3f}..{ended:9.3f} "
                f"({span:6.3f} с, манифест {want:6.3f} с, "
                f"расхождение границы {began - grid.start(cut):+.3f} с)"
            )
    print(f"худшее расхождение границы с манифестом: {worst:.3f} с")

    print("\nбайты видео по сегментам:")
    same = True
    for slot in range(max(starts), args.upto + 1):
        seen = {}
        for start, (out, _) in runs.items():
            path = out / f"v{slot}.ts"
            seen[start] = video_md5(path) if path.exists() else ("нет", 0)
        agree = len({h for h, _ in seen.values()}) == 1
        same &= agree
        line = " · ".join(f"со слота {s}: {h} {n} Б" for s, (h, n) in seen.items())
        print(f"  v{slot}: {line}  {'совпало' if agree else 'РАЗНОЕ'}")
    print("\nитог:", "нарезка детерминирована" if same else "НАРЕЗКА РАЗЪЕХАЛАСЬ")


if __name__ == "__main__":
    main()
