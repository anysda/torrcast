"""Секундомер холодного старта: гоняет настоящий `cast` и печатает разбивку по фазам.

Метрика §7.1 SPEC-v2 — **от Enter'а после последнего вопроса до готовности LOAD**
(манифест плюс первый сегмент). Телевизор при этом не трогается вовсе: приёмник в
конфиге замера — ``mock``, ни одного пакета к ТВ не уходит.

    python3 scripts/startbench.py "моана 2" --cold
    python3 scripts/startbench.py "моана 2"          # прогретый кэш карт

``--cold`` — честный холодный старт: раздачи из TorrServer снесены, кэш карт очищен.
Ответы на вопросы подаются мгновенно (``--think 0``), то есть меряется худший случай:
прогрев под меню не успевает ничего дать. ``--think N`` — сколько секунд «думает»
человек над каждым вопросом.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.timing import mark, read, report

BENCH = Path("/root/bench")
CAST = "/opt/torrcast/venv/bin/cast"


def config(prod: Path, port: int) -> Path:
    """Конфиг замера: тот же стенд, но приёмник mock и свой каталог сегментов."""
    BENCH.mkdir(parents=True, exist_ok=True)
    body = json.loads(prod.read_text("utf-8"))
    body["receiver"] = "mock"
    body["hls_dir"] = "/dev/shm/torrcast-bench"
    body["hls_port"] = port
    # ⚠️ Ночное ограждение: ни одного пакета к телевизору. Адрес раздачи задаётся руками,
    # чтобы показ не искал маршрут до ТВ, а приёмник замера — mock, он никуда не звонит.
    body["hls_base_url"] = f"http://127.0.0.1:{port}"
    body["tv"] = ""
    path = BENCH / "config.json"
    path.write_text(json.dumps(body, indent=2), "utf-8")
    return path


def cold(url: str, state: Path) -> None:
    """Сбросить всё, что делает старт тёплым: раздачи TorrServer и кэш карт."""
    import requests

    with contextlib.suppress(Exception):
        found = requests.post(f"{url}/torrents", json={"action": "list"}, timeout=20).json()
        for item in found or []:
            requests.post(
                f"{url}/torrents", json={"action": "rem", "hash": item.get("hash")}, timeout=20
            )
    shutil.rmtree(state.parent / "keys", ignore_errors=True)


def watch_segment(
    stop: threading.Event, seen: threading.Event, out: str = "/dev/shm/torrcast-bench"
) -> None:
    """Отметить момент, когда первый сегмент **дописан**, с точностью до 50 мс.

    Дописан он тогда, когда ffmpeg открыл следующий: ``pack/v1.ts`` появился — значит
    ``v0.ts`` целый (:meth:`torrcast.stream.Packer.publish`). Это и есть «готовность LOAD»
    по метрике §7.1: манифест статичен и готов вместе с сеткой, ждать остаётся только кусок.
    """
    pack = Path(out) / "pack"
    while not stop.is_set():
        with contextlib.suppress(OSError):
            if (pack / "v1.ts").exists() or (Path(out) / "v0.ts").exists():
                mark("первый сегмент дописан")
                seen.set()
                return
        stop.wait(0.05)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--cold", action="store_true")
    ap.add_argument("--think", type=float, default=0.0, help="пауза перед каждым ответом, с")
    ap.add_argument("--answers", default="\n\n\n\n\n")
    ap.add_argument("--prod-config", default="/etc/torrcast/config.json")
    ap.add_argument("--port", type=int, default=8081)
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--segment-wait", type=float, default=120.0)
    args = ap.parse_args()

    state = BENCH / "state.json"
    cfg = config(Path(args.prod_config), args.port)
    line = BENCH / "timeline.jsonl"
    line.unlink(missing_ok=True)
    state.unlink(missing_ok=True)  # старт без сохранённой позиции — это и есть холодный
    shutil.rmtree("/dev/shm/torrcast-bench", ignore_errors=True)
    torrserver = json.loads(cfg.read_text("utf-8"))["torrserver_url"]
    if args.cold:
        cold(torrserver, state)

    env = {
        **os.environ,
        "TORRCAST_CONFIG": str(cfg),
        "TORRCAST_STATE": str(state),
        "TORRCAST_TIMELINE": str(line),
    }
    os.environ["TORRCAST_TIMELINE"] = str(line)  # метки пишет и сам замер
    stop, seen = threading.Event(), threading.Event()
    threading.Thread(target=watch_segment, args=(stop, seen), daemon=True).start()
    began = time.monotonic()
    feed = args.answers if args.think <= 0 else None
    proc = subprocess.Popen(
        [CAST, args.query],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert proc.stdin is not None
    if feed is not None:
        proc.stdin.write(feed)
        proc.stdin.flush()
    else:  # человек думает: ответы уходят с задержкой, прогрев успевает поработать

        def think() -> None:
            for _ in range(5):
                time.sleep(args.think)
                with contextlib.suppress(OSError):
                    proc.stdin.write("\n")  # type: ignore[union-attr]
                    proc.stdin.flush()  # type: ignore[union-attr]

        threading.Thread(target=think, daemon=True).start()
    try:
        out, _ = proc.communicate(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
    total = time.monotonic() - began
    # CLI уходит, как только приёмник сказал «играю», — а первый сегмент к этому моменту
    # ещё пакуется. Метрика §7.1 — именно он, поэтому ждём его и только потом гасим показ.
    seen.wait(args.segment_wait)
    stop.set()
    subprocess.run([CAST, "stop"], env=env, capture_output=True, timeout=60, check=False)

    print(out.rstrip())
    print(f"\n--- лента фаз (ноль = Enter после последнего вопроса), всего {total:.1f} с ---")
    print(report(line, zero="ответы"))
    marks = {str(m["name"]): float(m["at"]) for m in read(line)}
    if "ответы" in marks and "упаковка пошла" in marks:
        print(f"\nМАНИФЕСТ ГОТОВ: {marks['упаковка пошла'] - marks['ответы']:.2f} с")
    if "ответы" in marks and "первый сегмент дописан" in marks:
        готово = marks["первый сегмент дописан"] - marks["ответы"]
        print(f"ГОТОВНОСТЬ LOAD (манифест + первый сегмент): {готово:.2f} с")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
