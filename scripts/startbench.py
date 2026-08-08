"""Секундомер холодного старта: гоняет настоящий `cast` и печатает разбивку по фазам.

Метрика — **от Enter'а после последнего вопроса до готовности LOAD** (манифест плюс
первый сегмент). Телевизор при этом не трогается вовсе: приёмник в конфиге замера —
``mock``, ни одного пакета к ТВ не уходит.

    python3 scripts/startbench.py "моана 2" --cold
    python3 scripts/startbench.py "моана 2"          # прогретый кэш карт
    python3 scripts/startbench.py --resume 776 --from-key movie:моана-2:2024 --cold-swarm

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
import pty
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
    """Конфиг замера: рабочий конфиг, но приёмник mock и свой каталог сегментов."""
    BENCH.mkdir(parents=True, exist_ok=True)
    body = json.loads(prod.read_text("utf-8"))
    body["receiver"] = "mock"
    body["hls_dir"] = "/dev/shm/torrcast-bench"
    body["hls_port"] = port
    # ⚠️ Ограждение: ни одного пакета к телевизору. Адрес раздачи задаётся руками,
    # чтобы показ не искал маршрут до ТВ, а приёмник замера - mock, он никуда не звонит.
    body["hls_base_url"] = f"http://127.0.0.1:{port}"
    body["tv"] = ""
    path = BENCH / "config.json"
    path.write_text(json.dumps(body, indent=2), "utf-8")
    return path


def cold(url: str, state: Path, keys: bool = True) -> None:
    """Сбросить то, что делает старт тёплым: раздачи TorrServer и кэш карт.

    ``keys=False`` — сбросить только рой. Это и есть честное «продолжение с середины»:
    файл уже играли, карта опорных кадров лежит в кэше, а вот раздачу TorrServer после
    перезагрузки (или после ``cast stop`` и суток простоя) греть надо заново.
    """
    import requests

    with contextlib.suppress(Exception):
        found = requests.post(f"{url}/torrents", json={"action": "list"}, timeout=20).json()
        for item in found or []:
            requests.post(
                f"{url}/torrents", json={"action": "rem", "hash": item.get("hash")}, timeout=20
            )
    if keys:
        shutil.rmtree(state.parent / "keys", ignore_errors=True)


def resume_state(state: Path, source: Path, key: str, position: float) -> str:
    """Положить в состояние замера копию рабочей записи с нужной позицией.

    ⚠️ Рабочее состояние пользователя читается и НЕ трогается: замер живёт в своём
    каталоге и со своим файлом. Запись нужна ровно затем, чтобы `cast` пошёл коротким
    путём («Продолжить? [Да/сначала]»), а не через поиск и меню.
    """
    entries = json.loads(source.read_text("utf-8"))
    if key not in entries:
        raise SystemExit(f"в {source} нет записи {key}; есть: {', '.join(entries)}")
    entry = dict(entries[key])
    entry["pos"] = position
    entry["done"] = False
    state.write_text(json.dumps({key: entry}, ensure_ascii=False), "utf-8")
    return str(entry.get("query") or key.split(":")[1])


def watch_segment(
    stop: threading.Event,
    seen: threading.Event,
    line: Path,
    out: str = "/dev/shm/torrcast-bench",
) -> None:
    """Отметить момент, когда первый нужный сегмент **дописан**, с точностью до 50 мс.

    Дописан он тогда, когда ffmpeg открыл следующий и показ выложил его наружу
    (:meth:`torrcast.stream.Packer.publish`). Это и есть «готовность LOAD»: манифест
    статичен и готов вместе с сеткой, ждать остаётся только кусок.

    ⚠️ «Нужный» — это сегмент **того места, откуда играем**, а не ``v0``. На продолжении с
    середины путать их нельзя: mock открывает поток через ``ffmpeg -ss``, а тот сначала
    дёргает начало плейлиста, показ честно допаковывает ещё и ``v0``, и по нему замер
    показал бы совсем не то, что увидит телевизор. Номер слота берётся из ленты меток —
    его печатает пробный прогон (:func:`torrcast.stream.pack_start`).
    """
    slot = 0
    while not stop.is_set():
        with contextlib.suppress(OSError, ValueError, KeyError):
            found = next((m for m in read(line) if m.get("name") == "пробный прогон"), None)
            if found is not None:
                slot = int(found["слот"])
        with contextlib.suppress(OSError):
            if (Path(out) / f"v{slot}.ts").exists():
                mark("первый сегмент дописан", слот=slot)
                seen.set()
                return
        stop.wait(0.05)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", default="")
    ap.add_argument("--cold", action="store_true")
    ap.add_argument("--cold-swarm", action="store_true", help="сбросить рой, кэш карт оставить")
    ap.add_argument("--resume", type=float, help="продолжение с этой секунды фильма")
    ap.add_argument("--from-key", default="", help="какую запись рабочего состояния копировать")
    ap.add_argument("--live-state", default="/var/lib/torrcast/state.json")
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
    state.unlink(missing_ok=True)  # старт без сохранённой позиции - это и есть холодный
    shutil.rmtree("/dev/shm/torrcast-bench", ignore_errors=True)
    torrserver = json.loads(cfg.read_text("utf-8"))["torrserver_url"]
    query = args.query
    if args.resume is not None:
        saved = resume_state(state, Path(args.live_state), args.from_key, args.resume)
        query = args.query or saved
    if args.cold or args.cold_swarm:
        cold(torrserver, state, keys=args.cold)

    env = {
        **os.environ,
        "TORRCAST_CONFIG": str(cfg),
        "TORRCAST_STATE": str(state),
        "TORRCAST_TIMELINE": str(line),
    }
    os.environ["TORRCAST_TIMELINE"] = str(line)  # метки пишет и сам замер
    stop, seen = threading.Event(), threading.Event()
    threading.Thread(target=watch_segment, args=(stop, seen, line), daemon=True).start()
    began = time.monotonic()
    # ⚠️ ``--think`` работает только через pty, и это не прихоть. Без терминала ask_line
    # штатно **не спрашивает вовсе** (чтобы не висеть на пайпе), поэтому ответы
    # уходили мгновенно, сколько ни задерживай запись в stdin, - то есть «человек думает»
    # на пайпе не воспроизводится в принципе, и прогреву под вопросом не достаётся ни
    # секунды. С pty `cast` видит терминал, ждёт Enter'а, и пауза становится настоящей.
    master = -1
    if args.think > 0:
        master, slave = pty.openpty()
        proc = subprocess.Popen(
            [CAST, query], env=env, stdin=slave, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True,
        )  # fmt: skip
        os.close(slave)

        def think() -> None:
            for _ in range(5):
                time.sleep(args.think)
                if proc.poll() is not None:
                    return
                with contextlib.suppress(OSError):
                    os.write(master, b"\n")

        threading.Thread(target=think, daemon=True).start()
    else:
        proc = subprocess.Popen(
            [CAST, query], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True,
        )  # fmt: skip
        assert proc.stdin is not None
        proc.stdin.write(args.answers)
        proc.stdin.flush()
    try:
        out, _ = proc.communicate(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
    total = time.monotonic() - began
    # CLI уходит, как только приёмник сказал «играю», - а первый сегмент к этому моменту
    # ещё пакуется. Метрика - именно он, поэтому ждём его и только потом гасим показ.
    seen.wait(args.segment_wait)
    stop.set()
    if master >= 0:
        with contextlib.suppress(OSError):
            os.close(master)
    subprocess.run([CAST, "stop"], env=env, capture_output=True, timeout=60, check=False)

    print(out.rstrip())
    marks = {str(m["name"]): float(m["at"]) for m in read(line)}
    # ⚠️ Ноль - Enter после последнего вопроса. Если такой метки в ленте нет (на пути
    # продолжения её может не быть), нулём становится запуск юнита: он идёт сразу за
    # ответом (замерено: 0.05 с) и есть всегда.
    zero = "ответы" if "ответы" in marks else "юнит"
    print(f"\n--- лента фаз (ноль = «{zero}»), всего {total:.1f} с ---")
    print(report(line, zero=zero))
    if zero in marks and "упаковка пошла" in marks:
        print(f"\nМАНИФЕСТ ГОТОВ: {marks['упаковка пошла'] - marks[zero]:.2f} с")
    if zero in marks and "первый сегмент дописан" in marks:
        готово = marks["первый сегмент дописан"] - marks[zero]
        print(f"ГОТОВНОСТЬ LOAD (манифест + первый сегмент): {готово:.2f} с")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
