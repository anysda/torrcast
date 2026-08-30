#!/usr/bin/env python3
"""Измерить стыки DTS видео после одного и нескольких заходов упаковщика."""

from __future__ import annotations

import argparse
import itertools
import json
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.grid_for import grid_for
from torrcast.adapters.stream_pack.pack_start import pack_start
from torrcast.adapters.stream_pack.packer import Packer


def video_dts(path: Path) -> list[float]:
    """Все DTS видео в одном продуктовом куске."""
    done = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "packet=dts_time",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = json.loads(done.stdout).get("packets", [])
    found = [float(row["dts_time"]) for row in rows if "dts_time" in row]
    if not found:
        raise RuntimeError(f"в {path} нет DTS видео")
    return found


def frame_period(source: Path) -> float:
    done = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=avg_frame_rate",
            "-of",
            "default=nw=1:nk=1",
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return 1.0 / float(Fraction(done.stdout.strip()))


def ranges(count: int, runs: int) -> list[tuple[int, int]]:
    """Разбить все ячейки ровно на ``runs`` соседних непустых заходов."""
    if not 1 <= runs <= count:
        raise ValueError(f"число заходов должно быть от 1 до {count}")
    return [(count * n // runs, count * (n + 1) // runs - 1) for n in range(runs)]


def pack(source: Path, work: Path, runs: int) -> tuple[list[Path], set[int]]:
    """Упаковать продуктовым трактом и вернуть куски по порядку."""
    url = source.resolve().as_uri()
    grid = grid_for(url, 0.0, say=lambda line: print(f"  продукт: {line}"))
    out = work / f"out-{runs}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    between: set[int] = set()
    for number, (first, last) in enumerate(ranges(grid.count, runs)):
        run = work / f"run-{runs}-{number}"
        at = pack_start(url, grid.start(first))
        command = ffmpeg_pack_command(url, 0, str(run), grid, first, at, readrate=0.0, until=last)
        packer = Packer.start(command, out, run, first, last=last, at=at, grid=grid)
        code = packer.proc.wait(timeout=240)
        if code != 0:
            raise RuntimeError(f"заход {number} упаковки сломан: {packer.why()}")
        packer.publish()
        print(f"  заход {number}: ячейки {first}..{last}, pack_start={at:.6f}")
        if number:
            between.add(first - 1)
    pieces = [out / f"v{slot}.ts" for slot in range(grid.count)]
    missing = [path.name for path in pieces if not path.exists()]
    if missing:
        raise RuntimeError(f"продукт не выложил: {', '.join(missing)}")
    return pieces, between


def seams(pieces: list[Path]) -> list[tuple[str, float]]:
    tape = [video_dts(path) for path in pieces]
    return [
        (f"{left.name}-{right.name}", min(right_dts) - max(left_dts))
        for (left, right), (left_dts, right_dts) in zip(
            itertools.pairwise(pieces), itertools.pairwise(tape), strict=True
        )
    ]


def show(title: str, values: list[tuple[str, float]], between: set[int], period: float) -> bool:
    clean = True
    print(f"\n{title}")
    for kind in ("внутри", "между"):
        selected = [
            (name, value)
            for n, (name, value) in enumerate(values)
            if (n in between) == (kind == "между")
        ]
        rendered = ", ".join(f"{name}={value:+.4f}" for name, value in selected) or "нет"
        print(f"  {kind}: {rendered}")
        counts: dict[str, int] = {}
        for _name, value in selected:
            key = f"{value:+.4f}"
            counts[key] = counts.get(key, 0) + 1
            clean &= abs(value - period) < 0.0001
        distribution = ", ".join(f"{key} x{count}" for key, count in counts.items())
        print("  распределение:", distribution or "нет")
    print(f"  приговор: {'ЗЕЛЁНЫЙ' if clean else 'КРАСНЫЙ'} (норма={period:+.4f})")
    return clean


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("clip", type=Path)
    ap.add_argument("--runs", type=int, default=8)
    ap.add_argument("--work", type=Path, default=Path("/tmp/tc797-runseams"))
    args = ap.parse_args()
    shutil.rmtree(args.work, ignore_errors=True)
    args.work.mkdir(parents=True)
    period = frame_period(args.clip)
    print(f"период кадра: {period:+.7f} с")
    control, _ = pack(args.clip, args.work, 1)
    ok_control = show(
        "ПОЛОЖИТЕЛЬНЫЙ КОНТРОЛЬ: один непрерывный заход",
        seams(control),
        set(),
        period,
    )
    broken = [control[0], control[2]]
    ok_broken = show("СЛОМАННЫЙ КОНТРОЛЬ: v1 нарочно выброшен", seams(broken), set(), period)
    corpus, boundaries = pack(args.clip, args.work, args.runs)
    ok_corpus = show(
        f"ПРОДУКТОВЫЙ КОРПУС: {args.runs} заходов копией", seams(corpus), boundaries, period
    )
    if not ok_control or ok_broken:
        print("контроли измерителя не прошли", file=sys.stderr)
        return 2
    return 0 if ok_corpus else 1


if __name__ == "__main__":
    raise SystemExit(main())
