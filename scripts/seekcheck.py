"""Локальный потребитель HLS: доказательство перемотки без 404 и без минут тишины.

Гоняет **настоящий** тракт показа — :class:`~torrcast.stream.Feed` и
:class:`~torrcast.stream.HlsServer` — и ходит в него по http на ``127.0.0.1``, как ходил
бы приёмник. Телевизора в этом скрипте нет и быть не может: ни одного пакета наружу.

Что меряется на каждом запросе: код ответа, сколько ждали тела и сколько байт приехало.
404 в отчёте — провал: живой ресивер, поймав его, не берёт LOAD ещё пару минут, поэтому
«файла не будет» показу разрешено отвечать только за концом фильма.

Сценарии (``--case``):

* ``back`` — упаковка от нуля, показ уходит вперёд за окно ``keep``, и с этого места
  запрашивается сегмент в самом начале фильма. Здесь когда-то запрос висел ``wait``
  секунд и кончался 404, потому что «ниже ``packer.first``» считалось «вот-вот
  допакуется»;
* ``mid`` — то же самое наоборот: упаковка начата с середины, показ ушёл вперёд, запрос
  уходит НИЖЕ места старта упаковки;
* ``fwd`` — регресс обычной перемотки вперёд: прыжок далеко за край упаковки;
* ``all`` — все три подряд в одном показе (по умолчанию).

    python3 scripts/seekcheck.py --file /dev/shm/clip.mkv
    python3 scripts/seekcheck.py --source "http://127.0.0.1:8090/stream?link=<hash>&index=1&play"
"""

from __future__ import annotations

import argparse
import functools
import http.server
import shutil
import socket
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from probeprofile import add_argument as add_profile_argument
from probeprofile import choose as choose_profile

from torrcast.cli import _layout
from torrcast.runtime.wire import wire
from torrcast.state import load_config
from torrcast.stream import (
    Feed,
    Grid,
    HlsServer,
    hls_dir,
    probe,
    segment_name,
)

#: Во сколько раз кусок вправе быть длиннее заказанного шага, прежде чем сетка перестанет
#: быть сеткой.
#:
#: 🔴 Фикстура ``tape.mkv``, лежавшая на стенде как «лёгкий материал», опорных кадров почти
#: не несёт: на шаге 10 с карта дала 9 сегментов, первый длиной 2901.8 с. Сеточный замер на
#: ней меряет один кусок в полчаса вместо сетки - и МОЛЧА, потому что сама сетка построена
#: честно (:func:`torrcast.stream.grid_for` ругается только на карту, не похожую на видео).
#: Порог с запасом: нарезка по опорным кадрам законно перебирает шаг на длину GOP (у
#: замеренного материала - до 1.5 шага), вчетверо - это уже не она.
GRID_FACTOR = 4.0
#: Меньше этого числа кусков сеточному замеру не хватит: перемотка вперёд, назад и заход с
#: середины требуют разных мест фильма, а не одного.
GRID_LEAST = 8


class _RangeHandler(http.server.SimpleHTTPRequestHandler):
    """Отдача файла с поддержкой Range: без неё карту опорных кадров не снять.

    ``SimpleHTTPRequestHandler`` Range не умеет вовсе и отвечает на него всем файлом —
    для :mod:`torrcast.keymap` это значит «тянем весь фильм ради индекса в хвосте».
    """

    path_on_disk: Path

    def do_GET(self) -> None:
        size = self.path_on_disk.stat().st_size
        raw = self.headers.get("Range", "")
        first, last = 0, size - 1
        if raw.startswith("bytes="):
            head, _, tail = raw[6:].partition("-")
            first = int(head) if head else 0
            last = min(int(tail), size - 1) if tail else size - 1
        with self.path_on_disk.open("rb") as handle:
            handle.seek(first)
            body = handle.read(last - first + 1)
        self.send_response(206 if raw else 200)
        self.send_header("Content-Type", "video/x-matroska")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(body)))
        if raw:
            self.send_header("Content-Range", f"bytes {first}-{last}/{size}")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        pass


class _QuietTCP(socketserver.ThreadingTCPServer):
    """ffmpeg рвёт соединение, дочитав индекс, — это норма, а не авария раздачи."""

    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request: object, client_address: object) -> None:
        pass


def free_port() -> int:
    """Свободный порт спрашивается у ядра, а не пишется в щупе константой.

    🔴 Порты 18098/18099 стояли тут числами, и два замера рядом на одном стенде падали с
    ``Address already in use``: параллельные прогоны были невозможны вовсе, а второй
    падал не по делу - и это уже стоило времени. ``bind`` на порт 0 отдаёт номер, который
    свободен сейчас; соединений на сокете не было, поэтому TIME_WAIT ему не грозит и
    раздача встаёт на то же место.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def unfit_grid(grid: Grid, step: float) -> str:
    """Чем сетка негодна для сеточного замера; пусто - годна.

    Смотрит не на фикстуру, а на то, что из неё вышло: сетка строится по опорным кадрам,
    и материал без них даёт «сетку» из нескольких получасовых кусков. Замер на такой
    сетке меряет что угодно, только не перемотку, и молчать об этом нельзя
    (:data:`GRID_FACTOR`).
    """
    if grid.count < GRID_LEAST:
        return f"в сетке всего {grid.count} сегментов - меньше {GRID_LEAST}"
    spans = [grid.span(k) for k in range(grid.count)]
    worst = max(spans)
    if worst > step * GRID_FACTOR:
        where = spans.index(worst)
        return (
            f"кусок v{where} длиной {worst:.1f} с при шаге {step:g} с "
            f"(в {worst / step:.0f} раз длиннее заказанного)"
        )
    return ""


def serve_file(path: Path) -> str:
    """Поднять мини-раздачу исходника на петле и вернуть его URL."""
    handler = type("_Bound", (_RangeHandler,), {"path_on_disk": path})
    port = free_port()
    server = _QuietTCP(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}/{path.name}"


def get(url: str, timeout: float) -> tuple[int, int, float]:
    """Один запрос потребителя: ``(код, байт, секунд ожидания)``."""
    began = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as answer:
            body = answer.read()
        return answer.status, len(body), time.monotonic() - began
    except urllib.error.HTTPError as exc:
        exc.read()
        return exc.code, 0, time.monotonic() - began
    except OSError as exc:
        print(f"  сеть: {exc}")
        return 0, 0, time.monotonic() - began


class Consumer:
    """Приёмник, которого нет: ходит за сегментами и ведёт счёт 404 и ожиданий."""

    def __init__(self, base: str, feed: Feed, timeout: float) -> None:
        self.base, self.feed, self.timeout = base, feed, timeout
        self.misses = 0
        self.worst = 0.0

    def take(self, slot: int, note: str = "") -> float:
        """Забрать сегмент, отчитаться и подвинуть позицию показа (с уборкой, как в _hold)."""
        code, size, waited = get(f"{self.base}/{segment_name(slot)}", self.timeout)
        self.worst = max(self.worst, waited)
        if code == 404:
            self.misses += 1
        self.feed.prune(self.feed.grid.start(slot))
        mark = "🔴 404" if code == 404 else f"{code}"
        print(
            f"  v{slot:<4} ({self.feed.grid.start(slot):7.1f} с) · {mark} · "
            f"{size / 1e6:6.2f} МБ · ждал {waited:5.1f} с · tmpfs "
            f"{self.feed.weight() / 1e6:5.0f} МБ{' · ' + note if note else ''}"
        )
        return waited

    def play(self, first: int, upto: float) -> int:
        """Крутить показ подряд с сегмента ``first``, пока не пройдём ``upto`` секунд фильма."""
        slot = first
        while self.feed.grid.start(slot) < upto and slot < self.feed.grid.count - 1:
            self.take(slot)
            slot += 1
        return slot - 1


def case_back(user: Consumer, keep: float) -> None:
    """Упаковка от нуля, показ ушёл вперёд, запрос — в самое начало фильма."""
    print("\n- сценарий «упаковка с нуля → показ ушёл вперёд → запрос далеко назад» -")
    user.feed.restart(0)
    last = user.play(0, keep + 3 * user.feed.grid.span(0))
    left = sorted(s for s in _slots(user.feed) if s <= 1)
    print(f"  показ на {user.feed.grid.end(last):.0f} с; начало фильма в tmpfs: {left or 'нет'}")
    waited = user.take(0, "перемотка в начало")
    print(f"  ⇒ ждали {waited:.1f} с (было: {user.feed.wait:.0f} с тишины и 404)")


def case_mid(user: Consumer, keep: float) -> None:
    """То же наоборот: упаковка начата с середины, запрос уходит ниже её старта."""
    grid = user.feed.grid
    start = grid.slot_at(grid.duration / 2)
    print(f"\n- сценарий «упаковка с середины (v{start}) → показ вперёд → запрос ниже старта» -")
    user.feed.restart(start)
    last = user.play(start, grid.start(start) + keep + 3 * grid.span(start))
    print(f"  показ на {grid.end(last):.0f} с")
    waited = user.take(max(start - 5, 0), "перемотка ниже места старта упаковки")
    print(f"  ⇒ ждали {waited:.1f} с")


def case_start(user: Consumer, at: float) -> None:
    """Голый заход: упаковка с нужного места и первый кусок - больше ничего.

    Это и есть метрика человека: от «поехали» до готовности первого куска. Остальные
    сценарии меряют показ, который уже идёт, а тут показа ещё нет вовсе.
    """
    grid = user.feed.grid
    slot = grid.slot_at(at)
    print(
        f"\n- заход с {at:.1f} с (v{slot}, [{grid.start(slot):.3f}..{grid.end(slot):.3f}), "
        f"{grid.span(slot):.1f} с) -"
    )
    began = time.monotonic()
    user.feed.restart(slot)
    waited = user.take(slot, "первый кусок захода")
    print(
        f"  ⇒ ПЕРВЫЙ КУСОК ЗАХОДА: {time.monotonic() - began:.1f} с (ожидание тела {waited:.1f} с)"
    )


def case_fwd(user: Consumer) -> None:
    """Регресс: обычная перемотка вперёд далеко за край упаковки."""
    grid = user.feed.grid
    far = min(grid.slot_at(grid.duration * 0.8), grid.count - 2)
    print(f"\n- регресс: перемотка вперёд на v{far} ({grid.start(far):.0f} с) -")
    waited = user.take(far, "прыжок вперёд")
    for slot in range(far + 1, far + 4):  # префетч живого приёмника: шесть кусков разом
        user.take(slot)
    print(f"  ⇒ первый кусок за {waited:.1f} с, префетч подхватился")


def _slots(feed: Feed) -> list[int]:
    from torrcast.stream import segment_slot

    return [s for s in (segment_slot(p.name) for p in feed.out.glob("v*.ts")) if s >= 0]


def trace_steer() -> None:
    """Печатать каждое решение показа об упаковке: без этого «почему перезапустился» —
    гадание, а гадать на этом месте уже пробовали, и правку пришлось откатывать.
    """
    raw = Feed._steer

    def traced(self: Feed, slot: int) -> bool:
        before = self.packer
        was = (before.poll(), before.first, before.edge) if before else None
        hope = raw(self, slot)
        after = self.packer
        now = (after.poll(), after.first, after.edge) if after else None
        print(f"    · решение v{slot}: код/first/край {was} → {now}, ждём={hope}")
        return hope

    Feed._steer = traced  # type: ignore[method-assign]


def main() -> int:
    # Медиатракт сценарию раздаёт композиционный корень: без него лента показа не
    # знает ни имён сегментов, ни чем паковать.
    wire()
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source", help="URL потока (TorrServer)")
    source.add_argument("--file", help="локальный файл - поднимем ему Range-раздачу сами")
    parser.add_argument("--case", default="all", choices=("all", "back", "mid", "fwd", "start"))
    parser.add_argument("--at", type=float, default=0.0, help="с какой секунды заходить (start)")
    parser.add_argument("--out", default="/dev/shm/seekcheck", help="каталог показа")
    parser.add_argument("--step", type=float, default=10.0, help="шаг сетки, с")
    parser.add_argument("--keep", type=float, default=120.0, help="окно позади показа, с")
    parser.add_argument("--burst", type=float, default=60.0)
    parser.add_argument("--readrate", type=float, default=1.0)
    parser.add_argument("--wait", type=float, default=120.0, help="сколько показ держит запрос")
    parser.add_argument("--trace", action="store_true", help="печатать решения об упаковке")
    parser.add_argument("--whole", action="store_true", help="перекодировать фильм целиком")
    parser.add_argument("--mbit", type=float, default=9.0, help="во сколько перекодировать")
    add_profile_argument(parser)
    args = parser.parse_args()

    if args.trace:
        trace_steer()

    url = args.source or serve_file(Path(args.file).resolve())
    media = probe(url)
    print(f"источник: {url}\nдлительность {media.duration:.1f} с, видео {media.video}")
    # 🔴 Сетка и решение о сплошном перекоде берутся ОДНИМ вызовом того же места, которым
    # их считает показ, а не собираются здесь заново. Пока щуп собирал их сам, он мерил
    # не тот тракт: на стенде (1080p10, потолок 9) показ пакует в цель 8.12 Мбит/с при
    # потолке кодера 8.77, а щуп паковал в 9.00 и 9.72 - на 10.8% мимо, потому что не
    # знал ни про ``fit`` от самого длинного куска, ни про то, что сетке обещают
    # ``maxrate``, а не цель.
    config, choice = choose_profile(load_config(), args.profile)
    config = replace(config, recode=True, recode_mbit=args.mbit, hls_segment=args.step)
    if args.whole:
        # Порог «тяжёл каждый кусок» опущен ниже любого веса: щуп меряет ИМЕННО сплошной
        # перекод, но решение о нём всё равно принимает показ, а не щуп.
        config = replace(config, bitrate_hard_mbit=-1.0)
    grid, whole = _layout(
        config,
        url,
        media.duration,
        media.video or "",
        max(0.0, media.video_bps / 1e6),
        say=print,
        depth=media.depth,
        profile=choice.profile,
        frame=media.frame,
        hdr=media.hdr,
    )
    if whole is not None:
        print(
            f"сплошной перекод: {whole.preset}, цель {whole.mbit:.2f} Мбит/с, "
            f"потолок кодера {whole.maxrate:.2f}, кадр {whole.out_frame}, тонемап {whole.hdr}"
        )
    unfit = unfit_grid(grid, args.step)
    if unfit:
        print(
            f"🔴 материал негоден для сеточного замера: {unfit}.\n"
            "   Опорных кадров в нём почти нет, и мерить перемотку по такой сетке "
            "нечего - возьми другой материал.",
            file=sys.stderr,
        )
        return 2

    out = hls_dir(args.out)
    feed = Feed(
        source=url,
        audio=0,
        out=out,
        grid=grid,
        readrate=args.readrate,
        burst=args.burst,
        keep=args.keep,
        wait=args.wait,
        log=functools.partial(print, "  упаковка:"),
        encode=whole,
    )
    port = free_port()
    server = HlsServer(out, host="127.0.0.1", port=port, feed=feed)
    server.start()
    base = f"http://127.0.0.1:{port}"
    user = Consumer(base, feed, timeout=args.wait + 30.0)
    began = time.monotonic()
    try:
        code, size, waited = get(f"{base}/index.m3u8", 30.0)
        print(f"манифест: {code}, {size} байт на {grid.count} сегментов - за {waited:.2f} с")
        if args.case == "start":
            case_start(user, args.at)
        if args.case in ("all", "back"):
            case_back(user, args.keep)
        if args.case in ("all", "mid"):
            case_mid(user, args.keep)
        if args.case in ("all", "fwd"):
            case_fwd(user)
    finally:
        feed.stop()
        server.stop()
        shutil.rmtree(out, ignore_errors=True)

    print(
        f"\nитог: 404 - {user.misses}, худшее ожидание {user.worst:.1f} с, "
        f"всего {time.monotonic() - began:.0f} с"
    )
    return 0 if user.misses == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
