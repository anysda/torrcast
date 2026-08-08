"""Сверка карты опорных кадров с самим файлом: врёт карта или не врёт.

Щуп родился из ложной тревоги: карту сверяли с метками готовых сегментов, видели ровно
+1.400 с на каждой границе и записали это в «у этого релиза карта расходится с реальными
метками». Расходился мультиплексор mpegts (:data:`torrcast.stream.MPEGTS_MUX_DELAY`), а
карта была точна. Чтобы такой вопрос закрывался замером за минуту, а не сутками, здесь
две независимые сверки одной и той же карты:

* **по байтам** — время из индекса против ``Timestamp`` кластера, на который индекс
  показывает, и против метки самого блока в нём. Это разбор EBML на месте, ffmpeg не
  участвует вовсе; стоит один Range-запрос на точку;
* **ffprobe** — тот же кадр глазами ffmpeg: он сам ищет по индексу и отдаёт ``pts_time``
  пакета. Проверяет заодно, что кадр действительно опорный (флаг ``K``).

    python3 scripts/mapcheck.py "http://127.0.0.1:8090/stream?link=<hash>&index=1&play"
    python3 scripts/mapcheck.py <url> --at 3955.243,3965.670   # прицельно по границам
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast import TorrcastError
from torrcast.keymap import HEAD_PEEK, Point, Reader, keyframes, video_track
from torrcast.mkv import CLUSTER, _uint, _vint, _walk
from torrcast.mkv import _Head as MkvHead

#: EBML-идентификаторы кластера, которые нужны сверке.
TIMESTAMP = 0xE7
SIMPLE_BLOCK = 0xA3
BLOCK_GROUP = 0xA0
BLOCK = 0xA1
#: Полкадра 24 к/с: точнее метка в контейнере с точностью до миллисекунды и не бывает.
TOLERANCE = 0.021


def cluster_at(buf: bytes, scale: float, track: int) -> tuple[float | None, float | None, bool]:
    """(время кластера, время первого блока дорожки, опорный ли он) — из сырых байт."""
    found = _walk(buf, 0, min(32, len(buf)))
    if not found or found[0][0] != CLUSTER:
        return None, None, False
    _, size, data = found[0]
    end = min(len(buf), data + size)
    raw = None
    for ident, b_size, b_data in _walk(buf, data, end):
        if ident == TIMESTAMP:
            raw = _uint(buf, b_data, b_size)
        elif ident in (SIMPLE_BLOCK, BLOCK_GROUP) and raw is not None:
            block = b_data
            if ident == BLOCK_GROUP:
                inner = [e for e in _walk(buf, b_data, min(end, b_data + b_size)) if e[0] == BLOCK]
                if not inner:
                    continue
                block = inner[0][2]
            number, after = _vint(buf, block, keep_marker=False)
            if number != track:
                continue
            rel = int.from_bytes(buf[after : after + 2], "big", signed=True)
            key = ident == BLOCK_GROUP or bool(buf[after + 2] & 0x80)
            return raw * scale / 1e9, (raw + rel) * scale / 1e9, key
    return (raw * scale / 1e9 if raw is not None else None), None, False


def ffprobe_at(url: str, at: float) -> tuple[float | None, bool]:
    """Метка первого видеопакета от ``at`` глазами ffmpeg и опорный ли он."""
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
         "packet=pts_time,flags", "-of", "csv=p=0", "-read_intervals", f"{at:.3f}%+#1", url],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    line = done.stdout.strip().splitlines()
    if not line:
        return None, False
    parts = line[0].split(",")
    try:
        return float(parts[0]), len(parts) > 1 and parts[1].startswith("K")
    except ValueError:
        return None, False


def picks(video: list[Point], wanted: str, count: int) -> list[Point]:
    if wanted:
        return [min(video, key=lambda p: abs(p.at - float(x))) for x in wanted.split(",")]
    step = max(1, len(video) // (count + 1))
    return [video[k * step] for k in range(1, count + 1)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("url")
    ap.add_argument("--at", default="", help="секунды через запятую: какие точки сверять")
    ap.add_argument("--points", type=int, default=6, help="сколько точек взять вразброс")
    ap.add_argument("--no-ffprobe", action="store_true", help="только сверка по байтам")
    args = ap.parse_args()

    try:
        found = keyframes(args.url)
    except TorrcastError as exc:
        raise SystemExit(str(exc)) from exc
    track = video_track(found.points)
    video = [p for p in found.points if p.track == track]
    print(
        f"карта: {len(video)} опорных кадров дорожки {track}, фильм {found.duration:.3f} с, "
        f"контейнер {found.kind}"
    )
    if found.kind != "mkv":
        print("сверка по байтам умеет пока только mkv - остаётся ffprobe")

    reader = Reader(args.url)
    facts = MkvHead(reader.read(0, HEAD_PEEK)) if found.kind == "mkv" else None
    scale = float(facts.scale) if facts else 1e6
    worst = 0.0
    bad = 0
    for point in picks(video, args.at, args.points):
        line = f"  карта {point.at:10.3f} @{point.offset:12d}"
        if found.kind == "mkv":
            ts, block, key = cluster_at(reader.read(point.offset, 64 << 10), scale, track)
            for what, got in (("кластер", ts), ("блок", block)):
                if got is None:
                    line += f" | {what} не прочитан"
                    bad += 1
                    continue
                worst = max(worst, abs(got - point.at))
                bad += abs(got - point.at) > TOLERANCE
                line += f" | {what} {got:10.3f} (Δ {got - point.at:+.3f})"
            line += " | опорный" if key else " | ⚠️ НЕ опорный"
            bad += not key
        if not args.no_ffprobe:
            got, key = ffprobe_at(args.url, point.at)
            if got is None:
                line += " | ffprobe молчит"
                bad += 1
            else:
                worst = max(worst, abs(got - point.at))
                bad += abs(got - point.at) > TOLERANCE
                line += f" | ffprobe {got:10.3f} (Δ {got - point.at:+.3f})"
                line += "" if key else " ⚠️ НЕ опорный"
                bad += not key
        print(line)
    print(
        f"худшее расхождение {worst:.3f} с, допуск {TOLERANCE} с, "
        f"взято {reader.taken / 1e6:.2f} МБ за {reader.requests} запросов"
    )
    print("итог:", "карта совпадает с файлом" if not bad else f"КАРТА РАСХОДИТСЯ ({bad})")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
