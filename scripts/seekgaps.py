#!/usr/bin/env python3
"""Измерить пробелы между местами посадки ``-ss`` на границах сетки.

Щуп повторяет пробный прогон упаковки: копирует один видеокадр в MPEG-TS и читает
метку первого пакета. Код возврата ffmpeg не считается достаточным признаком успеха:
ошибка демультиплексирования в stderr отвергает прогон и отправляет границу на повтор.

    python3 scripts/seekgaps.py URL --duration 7200
    python3 scripts/seekgaps.py URL --duration 7200 --step 10 --retries 2

На stdout пишется JSONL: сначала одна строка на границу, затем итоговая строка. Щуп
ничего не знает о каталоге, раздаче и стенде; URL и длительность задаёт измеряющий.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Landing:
    asked: float
    stood: float | None
    attempts: int
    error: str = ""


def boundaries(duration: float, step: float) -> list[float]:
    """Все ненулевые начала сегментов той же равномерной сетки, что у упаковки."""
    count = max(1, math.ceil((max(duration, 0.0) - step / 2) / step))
    return [step * slot for slot in range(1, count)]


def _demux_error(stderr: str) -> str:
    for line in stderr.splitlines():
        folded = line.casefold()
        if "error during demuxing" in folded or "input/output error" in folded:
            return line.strip()
    return ""


def land(url: str, at: float, timeout: float) -> tuple[float | None, str]:
    """Один боевой пробный прогон; ошибка названа отдельно от места посадки."""
    with tempfile.TemporaryDirectory(prefix="seekgaps-") as tmp:
        first = Path(tmp) / "first.ts"
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-copyts", "-ss", f"{at:.3f}",
            "-i", url, "-map", "0:v:0", "-c", "copy", "-frames:v", "1",
            "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", "-y", str(first),
        ]  # fmt: skip
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, str(exc)
        demux = _demux_error(done.stderr)
        if done.returncode != 0 or demux:
            tail = demux or next(
                (line.strip() for line in reversed(done.stderr.splitlines()) if line.strip()),
                f"ffmpeg завершился с кодом {done.returncode}",
            )
            return None, tail
        try:
            found = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                 "packet=pts_time", "-of", "csv=p=0", "-read_intervals", "%+#1", str(first)],
                capture_output=True, text=True, timeout=timeout, check=True,
            )  # fmt: skip
            stood = float(found.stdout.strip().splitlines()[0].split(",")[0])
        except (OSError, subprocess.SubprocessError, IndexError, ValueError) as exc:
            return None, f"первый пакет не прочитан: {exc}"
        return stood, ""


def measure(url: str, at: float, timeout: float, retries: int) -> Landing:
    error = ""
    for attempt in range(1, retries + 2):
        stood, error = land(url, at, timeout)
        if stood is not None:
            return Landing(at, stood, attempt)
    return Landing(at, None, retries + 1, error)


def summary(rows: list[Landing], duration: float, step: float) -> dict[str, object]:
    reached = sorted({row.stood for row in rows if row.stood is not None})
    gaps = [(left, right, right - left) for left, right in zip(reached, reached[1:], strict=False)]
    widest = max(gaps, key=lambda gap: gap[2], default=(None, None, 0.0))
    failed = [row.asked for row in rows if row.stood is None]
    return {
        "итог": True,
        "длительность": duration,
        "шаг": step,
        "границ": len(rows),
        "измерено": len(rows) - len(failed),
        "ошибок": len(failed),
        "недоступные границы": failed,
        "различных посадок": len(reached),
        "самый широкий провал": round(widest[2], 6),
        "между": [widest[0], widest[1]],
        "шире 80 с": widest[2] > 80.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--step", type=float, default=10.0)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args()
    if args.duration <= 0 or args.step <= 0 or args.timeout <= 0 or args.retries < 0:
        parser.error("длительность, шаг и таймаут должны быть положительными, повторы — неотрицательны")
    rows = []
    for at in boundaries(args.duration, args.step):
        row = measure(args.url, at, args.timeout, args.retries)
        rows.append(row)
        print(json.dumps({
            "граница": row.asked, "посадка": row.stood, "попыток": row.attempts,
            "ошибка": row.error,
        }, ensure_ascii=False), flush=True)
    report = summary(rows, args.duration, args.step)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 2 if report["ошибок"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
