#!/usr/bin/env python3
"""Проверить непрерывность DTS на стыках готовых кусков."""

from __future__ import annotations

import itertools
import json
import subprocess
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


@dataclass(frozen=True)
class Edge:
    """Край потока: первая и последняя метки и шаг последнего кадра."""

    first: Fraction
    last: Fraction
    step: Fraction


def edges(path: Path) -> dict[str, Edge]:
    """Прочитать края видео и звука вместе с их собственными шагами."""
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_packets",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(probe.stdout)
    streams = {
        row["index"]: (row["codec_type"], Fraction(row["time_base"]))
        for row in data["streams"]
        if row["codec_type"] in ("video", "audio")
    }
    found: dict[str, list[tuple[Fraction, Fraction]]] = {"video": [], "audio": []}
    for packet in data["packets"]:
        stream = streams.get(packet["stream_index"])
        if stream is None or "dts" not in packet or "duration" not in packet:
            continue
        kind, time_base = stream
        found[kind].append((int(packet["dts"]) * time_base, int(packet["duration"]) * time_base))
    result: dict[str, Edge] = {}
    for _index, (kind, time_base) in streams.items():
        rows = found[kind]
        if rows:
            # DTS целочисленны в шкале потока. Номинальный кадр иногда округляется
            # вверх на один её тик, поэтому этот тик тоже приходит из ffprobe.
            result[kind] = Edge(
                min(mark for mark, _duration in rows),
                max(mark for mark, _duration in rows),
                max(duration for _mark, duration in rows) + time_base,
            )
    return result


def main(names: list[str]) -> int:
    groups: list[list[Path]] = [[]]
    for name in names:
        if name == "--":
            groups.append([])
        else:
            groups[-1].append(Path(name))
    legs = ("упаковка копией", "непрерывность перекода", "выкладка зрителю")
    broken = False
    for leg, pieces in zip(legs, groups, strict=False):
        if len(pieces) < 2:
            raise SystemExit("сторожу стыков нужно хотя бы два куска")
        timeline = [edges(piece) for piece in pieces]
        for piece, found in zip(pieces, timeline, strict=True):
            if "video" not in found:
                print(f"{leg}: {piece.name} - ни одного видеокадра", file=sys.stderr)
                broken = True
        for seam, (left, right) in enumerate(itertools.pairwise(timeline), start=1):
            for stream, label in (("video", "видео"), ("audio", "звук")):
                if stream not in left or stream not in right:
                    continue
                gap = right[stream].first - left[stream].last
                if gap <= 0:
                    print(
                        f"{leg}, стык {seam}: {label}, откат {float(-gap):.4f} с",
                        file=sys.stderr,
                    )
                    broken = True
                elif gap > left[stream].step:
                    hole = gap - left[stream].step
                    print(
                        f"{leg}, стык {seam}: {label}, дыра {float(hole):.4f} с "
                        f"(ход {float(gap):.4f} с, шаг {float(left[stream].step):.4f} с)",
                        file=sys.stderr,
                    )
                    broken = True
    return int(broken)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
