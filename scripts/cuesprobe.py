"""Секундомер снятия карты опорных кадров: где именно уходят 13–24 с холодного роя.

Не часть продукта — измерительный щуп (§7.1 SPEC-v2). Раскладывает :func:`torrcast.mkv.keyframes`
на отдельные Range-запросы и печатает цену каждого: сколько байт и сколько секунд.

    python3 scripts/cuesprobe.py --magnet 'magnet:?...' [--head 262144]
"""

from __future__ import annotations

import argparse
import json
import sys
import time

sys.path.insert(0, "/root/torrcast")

from torrcast.mkv import (
    CLUSTER,
    CUES,
    DURATION,
    INFO,
    SEEK,
    SEEK_HEAD,
    SEEK_ID,
    SEEK_POSITION,
    SEGMENT,
    TIMESTAMP_SCALE,
    Reader,
    _uint,
    _walk,
)
from torrcast.stream import TorrServer, pick_video_file


def head_scan(buf: bytes) -> tuple[int | None, int, float]:
    segment = next((d for i, _, d in _walk(buf, 0, len(buf)) if i == SEGMENT), None)
    if segment is None:
        return None, 1_000_000, 0.0
    cues_at, scale, duration = None, 1_000_000, 0.0
    for ident, size, data in _walk(buf, segment, len(buf)):
        end = min(len(buf), data + size)
        if ident == SEEK_HEAD:
            for _, seek_size, seek in [e for e in _walk(buf, data, end) if e[0] == SEEK]:
                what = which = None
                for sub, sub_size, sub_data in _walk(buf, seek, seek + seek_size):
                    if sub == SEEK_ID:
                        what = _uint(buf, sub_data, sub_size)
                    elif sub == SEEK_POSITION:
                        which = _uint(buf, sub_data, sub_size)
                if what == CUES and which is not None:
                    cues_at = segment + which
        elif ident == INFO:
            for sub, sub_size, sub_data in _walk(buf, data, end):
                if sub == TIMESTAMP_SCALE:
                    scale = _uint(buf, sub_data, sub_size)
                elif sub == DURATION:
                    duration = float(
                        __import__("struct").unpack(
                            ">f" if sub_size == 4 else ">d", buf[sub_data : sub_data + sub_size]
                        )[0]
                    )
        elif ident == CLUSTER:
            break
    return cues_at, scale, duration


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--magnet", required=True)
    ap.add_argument("--head", type=int, default=4 << 20)
    ap.add_argument("--tail", type=int, default=1 << 20, help="сколько берём одним куском с хвоста")
    ap.add_argument("--url", default="http://127.0.0.1:8090")
    ap.add_argument("--drop", action="store_true", help="снести раздачу после замера")
    args = ap.parse_args()

    ts = TorrServer(args.url)
    began = time.monotonic()
    h = ts.add(args.magnet)
    files = ts.wait_files(h, timeout=90)
    want = pick_video_file(files)
    source = ts.stream_url(h, want.index)
    meta = time.monotonic() - began
    print(f"метаданные {meta:.2f} с · файл {want.name[:70]} · {want.size / 1e9:.2f} ГБ")

    out: dict[str, float] = {"meta": meta}
    reader = Reader(source)

    t = time.monotonic()
    head = reader.read(0, args.head)
    out["head"] = time.monotonic() - t
    print(f"голова {len(head) / 1e6:.2f} МБ — {out['head']:.2f} с")

    cues_at, scale, duration = head_scan(head)
    print(f"  Cues на {cues_at} (файл {want.size}), длина {duration * scale / 1e9:.0f} с")
    if cues_at is None:
        return 1
    print(f"  хвост это или голова: {cues_at / want.size * 100:.1f}% файла")

    t = time.monotonic()
    chunk = reader.read(cues_at, args.tail)
    out["tail1"] = time.monotonic() - t
    print(f"хвост одним куском {len(chunk) / 1e6:.2f} МБ — {out['tail1']:.2f} с")

    ident, size, data = _walk(chunk, 0, 32)[0]
    print(f"  Cues: id={ident:#x} тело {size} байт, влезло в кусок: {data + size <= len(chunk)}")
    if data + size > len(chunk):
        t = time.monotonic()
        rest = reader.read(cues_at + len(chunk), data + size - len(chunk))
        out["tail2"] = time.monotonic() - t
        print(f"добор тела {len(rest) / 1e6:.2f} МБ — {out['tail2']:.2f} с")

    out["total"] = sum(v for k, v in out.items() if k != "meta")
    print(json.dumps(out))
    if args.drop:
        ts.drop(h)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
