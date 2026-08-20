#!/usr/bin/env python3
"""Щуп накладных первого куска: раскладывает старт ffmpeg по фазам на живом входе.

Между ffmpeg и раздачей ставится записывающий кран: каждый Range-запрос запоминается
со своим временем, поэтому видно, когда процесс дожил до первого чтения входа, сколько
он читал голову файла и куда уходил дальше. Момент первого куска берётся из каталога
прогона, а не со слов ffmpeg.

Один вызов - одна ступень лестницы, три и больше прогонов подряд:

    python scripts/openprobe.py --url '<стрим>' --stage recode --seconds 10125 --runs 3

Ступени: ``spawn`` - только подъём процесса, входа нет вовсе; ``open`` - открытие входа
и один пакет; ``seek`` - то же с ``-ss``; ``copy`` и ``recode`` - настоящая команда
упаковки до первого куска. Разности соседних ступеней и есть слагаемые накладных.

Инструмент разработчика: в устанавливаемый пакет не входит.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.adapters.recode.encode import Encode
from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.film_keys import film_keys
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.grid_for import grid_for
from torrcast.adapters.stream_pack.pack_origin import pack_origin
from torrcast.adapters.stream_pack.pack_start import pack_start
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.hls_settings import PACK_LIST


class _Tap(BaseHTTPRequestHandler):
    """Кран между ffmpeg и раздачей: пропускает запрос и запоминает его времена."""

    protocol_version = "HTTP/1.1"
    upstream: ClassVar[str] = ""
    began: ClassVar[float] = 0.0
    hits: ClassVar[list[dict[str, float]]] = []

    def log_message(self, format: str, *args: Any) -> None:
        """Молчать: своя запись точнее и не мешает замеру."""

    def do_GET(self) -> None:
        """Провести запрос наверх и записать, когда он пришёл, ответил и кончился."""
        span = self.headers.get("Range", "")
        off = float(span.split("=", 1)[1].split("-", 1)[0] or 0) if "=" in span else 0.0
        # Запись заводится СРАЗУ и дописывается по ходу: длинный запрос живёт весь прогон и
        # к концу замера ещё висит, а именно он и есть чтение места, откуда играем.
        hit: dict[str, float] = {
            "заход": time.monotonic() - _Tap.began,
            "смещение": off,
            "ответ": float("nan"),
            "конец": float("nan"),
            "байт": 0.0,
        }
        _Tap.hits.append(hit)
        request = urllib.request.Request(_Tap.upstream + self.path)
        if span:
            request.add_header("Range", span)
        size = 0
        try:
            with urllib.request.urlopen(request, timeout=120) as answer:
                hit["ответ"] = time.monotonic() - _Tap.began
                self.send_response(int(answer.status))
                for name in ("Content-Length", "Content-Range", "Content-Type", "Accept-Ranges"):
                    value = answer.headers.get(name)
                    if value is not None:
                        self.send_header(name, value)
                self.end_headers()
                while True:
                    piece = answer.read(1 << 16)
                    if not piece:
                        break
                    self.wfile.write(piece)
                    size += len(piece)
                    hit["байт"] = float(size)
        except OSError:
            # ffmpeg рвёт соединение, когда уходит на другое место: это не ошибка замера,
            # а ровно тот момент, когда прежнее место ему стало не нужно.
            pass
        hit["байт"] = float(size)
        hit["конец"] = time.monotonic() - _Tap.began
        self.close_connection = True


def tap(upstream: str) -> ThreadingHTTPServer:
    """Поднять кран и вернуть его; адрес читается из ``server_address``."""
    _Tap.upstream = upstream.rstrip("/")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Tap)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def command(stage: str, url: str, grid: Grid, slot: int, audio: int, run: Path) -> list[str]:
    """Команда ступени: чем выше ступень, тем больше работы делает тот же ffmpeg."""
    if stage == "spawn":
        return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                "-i", "nullsrc=s=64x64:d=0.04", "-frames:v", "1", "-f", "null", "-"]  # fmt: skip
    if stage in ("open", "seek"):
        head = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
        if stage == "seek" and slot > 0:
            head += ["-ss", f"{grid.start(slot):.3f}"]
        return [*head, "-i", url, "-map", "0:v:0", "-map", f"0:a:{audio}", "-c", "copy",
                "-frames:v", "1", "-f", "null", "-"]  # fmt: skip
    encode = Encode(preset="ultrafast", mbit=9.0, frame=1080) if stage == "recode" else None
    return ffmpeg_pack_command(
        url, audio, str(run), grid, slot, grid.start(slot),
        readrate=1.0, burst=60.0, encode=encode,
    )  # fmt: skip


def watch(
    run: Path, slot: int, stop: threading.Event, seen: dict[str, float], began: float
) -> None:
    """Отметить появление первого куска и его закрытие (строку в списке резов)."""
    piece, listing = run / f"v{slot}.ts", run / PACK_LIST
    while not stop.is_set():
        if "кусок" not in seen and piece.exists():
            seen["кусок"] = time.monotonic() - began
        if listing.exists() and listing.stat().st_size > 0:
            seen["закрыт"] = time.monotonic() - began
            return
        stop.wait(0.005)


def prelude(url: str, seconds: float, slot: int, marks: dict[str, float]) -> tuple[Grid, float]:
    """То, что показ делает ДО ffmpeg упаковки: карта, начало ленты, место захода.

    Каждое слагаемое отмечается само, потому что два из трёх поднимают свои процессы
    (ffprobe у начала ленты, ffmpeg с ffprobe у пробного прогона) и открывают тот же
    вход, что и упаковщик.
    """
    began = time.monotonic()

    def timed_keys(source: str) -> FilmKeys:
        keys = film_keys(source)
        marks["карта"] = time.monotonic() - began
        return keys

    def timed_origin(source: str) -> float:
        origin = pack_origin(source)
        marks["начало ленты"] = time.monotonic() - began - marks.get("карта", 0.0)
        return origin

    grid = grid_for(url, seconds, on_keys=True, keys_of=timed_keys, origin_of=timed_origin)
    marks["сетка"] = time.monotonic() - began
    at = pack_start(url, grid.start(slot)) if slot > 0 else 0.0
    marks["заход"] = time.monotonic() - began - marks["сетка"]
    marks["до упаковки"] = time.monotonic() - began
    return grid, at


def once(
    stage: str, url: str, grid: Grid, slot: int, audio: int, run: Path, wait: float
) -> dict[str, Any]:
    """Один прогон ступени: вернуть его фазы и всё, что видел кран."""
    shutil.rmtree(run, ignore_errors=True)
    run.mkdir(parents=True, exist_ok=True)
    _Tap.hits = []
    _Tap.began = began = time.monotonic()
    stop: threading.Event = threading.Event()
    seen: dict[str, float] = {}
    watcher = threading.Thread(target=watch, args=(run, slot, stop, seen, began), daemon=True)
    watcher.start()
    proc = subprocess.Popen(
        command(stage, url, grid, slot, audio, run),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    if stage in ("spawn", "open", "seek"):
        proc.wait(timeout=wait)
    else:
        while time.monotonic() - began < wait and "закрыт" not in seen:
            time.sleep(0.005)
        proc.terminate()
    stop.set()
    watcher.join(timeout=2.0)
    proc.wait(timeout=30)
    # Кран отвечает своими потоками: у оборванного запроса запись появляется на долю
    # секунды позже конца процесса, и без этой паузы он пропал бы из ленты замера.
    time.sleep(0.3)
    hits = list(_Tap.hits)
    return {
        "ступень": stage,
        "всего": round(time.monotonic() - began, 3),
        "первое_чтение": round(hits[0]["заход"], 3) if hits else None,
        "запросов": len(hits),
        "кусок": round(seen["кусок"], 3) if "кусок" in seen else None,
        "закрыт": round(seen["закрыт"], 3) if "закрыт" in seen else None,
        "кран": [{k: round(v, 3) for k, v in hit.items()} for hit in hits],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="стрим раздачи, как его видит показ")
    ap.add_argument(
        "--stage", required=True, choices=("spawn", "open", "seek", "copy", "recode", "full")
    )
    ap.add_argument("--seconds", type=float, required=True, help="длительность фильма")
    ap.add_argument("--slot", type=int, default=0, help="с какого куска сетки заходим")
    ap.add_argument("--audio", type=int, default=0)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--flat", action="store_true", help="ровная сетка вместо карты кадров")
    ap.add_argument("--dir", default="/dev/shm/openprobe")
    ap.add_argument("--wait", type=float, default=180.0)
    ap.add_argument("--out", default="", help="куда дописывать строки JSON")
    args = ap.parse_args()

    split = urllib.parse.urlsplit(args.url)
    server = tap(f"{split.scheme}://{split.netloc}")
    port = server.server_address[1]
    through = urllib.parse.urlunsplit(("http", f"127.0.0.1:{port}", split.path, split.query, ""))
    # Сетка строится ОДИН раз и до всякого замера: показ её тоже строит один раз, а карта
    # опорных кадров стоит своих Range-запросов и накладными первого куска не является.
    ready: dict[str, float] = {}
    grid = Grid.uniform(args.seconds)
    if args.stage != "full":
        if not args.flat:
            grid = grid_for(args.url, args.seconds, on_keys=True)
        print(
            f"сетка: {grid.count} кусков, по кадрам: {grid.on_keys}, кран: {port}",
            file=sys.stderr,
        )
    for number in range(args.runs):
        if args.stage == "full":
            ready = {}
            grid, _ = prelude(args.url, args.seconds, args.slot, ready)
        stage = "recode" if args.stage == "full" else args.stage
        found = once(stage, through, grid, args.slot, args.audio, Path(args.dir), args.wait)
        found["до"] = {name: round(value, 3) for name, value in ready.items()}
        found["прогон"] = number
        line = json.dumps(found, ensure_ascii=False)
        print(line, flush=True)
        if args.out:
            with open(args.out, "a", encoding="utf-8") as file:
                file.write(line + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
