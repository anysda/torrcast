#!/usr/bin/env python3
"""Замер стыка прогретого с живой упаковкой: приёмника тут нет вовсе.

Показ идёт по ленте: прогретый отрезок лежит на диске, дальше него плёнки нет ни у кого,
а источник на время замолкает - ровно как замолкает раздача, у которой просел рой. Мерятся
четыре числа: сколько ждал файла первый кусок ЗА концом прогретого, докуда лента считала показ
обеспеченным (:meth:`Feed.front`), сколько лежит в tmpfs (:meth:`Feed.weight`) и сколько всего
простояла плёнка.

    python scripts/seambench.py --clip clip.mp4 --seconds 600 --warm-until 40 \
        --mute-at 365 --mute 45

Источник - свой http поверх файла с рубильником: по команде он перестаёт отдавать байты,
не закрывая сокета. Это и есть молчание раздачи, а не обрыв входа: ffmpeg висит на чтении.

Инструмент разработчика: в устанавливаемый пакет не входит.
"""

from __future__ import annotations

import argparse
import http.server
import shutil
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.hls_dir import hls_dir
from torrcast.runtime.wire import wire
from torrcast.usecases.feed_pack.feed import Feed
from torrcast.usecases.warm.vault import Vault

#: Рубильник источника: пока поднят, ответ не двигается ни на байт, а сокет жив.
MUTED = threading.Event()
#: Файл, который раздаёт наш http: один на весь замер.
CLIP: Path = Path()


class _Source(http.server.BaseHTTPRequestHandler):
    """Раздача файла по http с поддержкой Range и рубильником молчания."""

    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _range(self, size: int) -> tuple[int, int]:
        header = self.headers.get("Range", "")
        if not header.startswith("bytes="):
            return 0, size - 1
        first, _, last = header[len("bytes=") :].partition("-")
        begin = int(first) if first else 0
        end = int(last) if last else size - 1
        return begin, min(end, size - 1)

    def do_GET(self) -> None:
        size = CLIP.stat().st_size
        begin, end = self._range(size)
        partial = self.headers.get("Range") is not None
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - begin + 1))
        if partial:
            self.send_header("Content-Range", f"bytes {begin}-{end}/{size}")
        self.end_headers()
        left = end - begin + 1
        with CLIP.open("rb") as stream:
            stream.seek(begin)
            while left > 0:
                while MUTED.is_set():
                    time.sleep(0.2)
                chunk = stream.read(min(1 << 16, left))
                if not chunk:
                    return
                try:
                    self.wfile.write(chunk)
                except OSError:
                    return
                left -= len(chunk)

    def do_HEAD(self) -> None:
        size = CLIP.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(size))
        self.end_headers()


class _Threaded(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def _warm_up(clip: Path, grid: Grid, vault: Vault, until: int, work: Path) -> int:
    """Уложить в прогретое куски ``0..until`` - тем же упаковщиком, что и живой показ."""
    run = work / "warmrun"
    run.mkdir(parents=True, exist_ok=True)
    command = ffmpeg_pack_command(
        clip.as_uri(), 0, str(run), grid, 0, 0.0, readrate=0.0, burst=0.0, until=until
    )
    subprocess.run(command, check=True, capture_output=True)
    laid = 0
    for slot in range(until + 1):
        piece = run / f"v{slot}.ts"
        if piece.exists():
            shutil.move(str(piece), str(vault.path(slot)))
            laid += 1
    shutil.rmtree(run, ignore_errors=True)
    return laid


def _clock(feed: Feed, played: dict[str, float], stop: threading.Event) -> None:
    """Часы показа: уборка и выкладка каждые две секунды, как в :func:`_hold`."""
    while not stop.is_set():
        feed.sweep()
        feed.prune(played["pos"])
        stop.wait(2.0)


def _mute_at(grid: Grid, began: float, played: dict[str, float], at: float, span: float) -> None:
    """Заткнуть источник, когда плёнка дойдёт до ``at``, и отпустить через ``span`` секунд."""
    while played["pos"] < at:
        time.sleep(0.2)
        if time.monotonic() - began > 3600:
            return
    MUTED.set()
    print(f"    источник замолчал на {played['pos']:.1f} с плёнки", flush=True)
    time.sleep(span)
    MUTED.clear()
    print(f"    источник вернулся на {played['pos']:.1f} с плёнки", flush=True)


def main() -> int:
    global CLIP
    wire()
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", required=True, help="файл, который смотрим")
    ap.add_argument("--seconds", type=float, required=True, help="длительность файла")
    ap.add_argument("--warm-until", type=int, required=True, help="последний прогретый кусок")
    ap.add_argument("--mute-at", type=float, required=True, help="на какой секунде плёнки молчим")
    ap.add_argument("--mute", type=float, default=45.0, help="сколько секунд молчит источник")
    ap.add_argument("--prefetch", type=float, default=20.0, help="за сколько секунд просят кусок")
    ap.add_argument("--dir", default="/dev/shm/seambench", help="каталог показа (tmpfs)")
    ap.add_argument("--work", default="/var/tmp/seambench", help="каталог прогретого")
    args = ap.parse_args()

    CLIP = Path(args.clip).resolve()
    work = Path(args.work)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    out = hls_dir(args.dir)
    for junk in out.glob("v*.ts"):
        junk.unlink(missing_ok=True)

    grid = Grid.uniform(args.seconds)
    vault = Vault(root=work / "warm", key="seambench", title="seambench")
    vault.open()
    laid = _warm_up(CLIP, grid, vault, args.warm_until, work)
    print(
        f"сетка: {grid.count} кусков по {grid.span(0):.1f} с; прогрето {laid} "
        f"(до {grid.end(args.warm_until):.1f} с плёнки), дальше плёнки нет ни у кого"
    )

    server = _Threaded(("127.0.0.1", 0), _Source)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/clip"

    feed = Feed(
        source=url,
        audio=0,
        out=out,
        grid=grid,
        vault=vault,
        log=lambda text: print(f"    показ: {text}", flush=True),
    )
    played = {"pos": 0.0}
    stop = threading.Event()
    threading.Thread(target=_clock, args=(feed, played, stop), daemon=True).start()

    began = time.monotonic()
    threading.Thread(
        target=_mute_at, args=(grid, began, played, args.mute_at, args.mute), daemon=True
    ).start()

    lost = 0.0
    seam = args.warm_until + 1
    print("кусок  откуда  ждал_с  запас_с  память_МБ  простой_с")
    try:
        for slot in range(grid.count):
            ask_at = max(0.0, grid.start(slot) - args.prefetch)
            while time.monotonic() - began - lost < ask_at:
                played["pos"] = min(time.monotonic() - began - lost, args.seconds)
                time.sleep(0.05)
            asked = time.monotonic()
            path = feed.segment(slot)
            waited = time.monotonic() - asked
            late = (asked + waited) - (began + lost + grid.start(slot))
            if late > 0:
                lost += late
            played["pos"] = max(0.0, min(time.monotonic() - began - lost, args.seconds))
            where = "нет" if path is None else ("прогрев" if path.parent == vault.dir else "живьём")
            slack = feed.front(grid.start(slot)) - grid.start(slot)
            mark = " <- стык" if slot == seam else ""
            print(
                f"{slot:5d}  {where:>7}  {waited:6.2f}  {slack:7.1f}  "
                f"{feed.weight() / 1e6:9.1f}  {lost:9.2f}{mark}",
                flush=True,
            )
            if path is None and slot > seam:
                print("файла не будет - замер прекращён", flush=True)
                break
            if slot >= seam + 6:
                break
    finally:
        stop.set()
        feed.stop()
        server.shutdown()
    print(f"ИТОГО: простой плёнки {lost:.2f} с")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
