#!/usr/bin/env python3
"""Секундомер цели: от команды человека до СДВИНУВШЕЙСЯ позиции на приёмнике.

Инструмент разработчика: в устанавливаемый пакет не входит. Гоняется НА СТЕНДЕ, рядом с
`cast` и `adb`, потому что мерит живой приёмник, а не заглушку.

    python3 scripts/framebench.py "матрица"                 # прогретый
    python3 scripts/framebench.py "матрица" --cold          # рой и карты снесены
    python3 scripts/framebench.py "матрица" --cold-swarm    # снесён только рой

Сосед :mod:`startbench` кончает замер на готовности LOAD (манифест плюс первый сегмент) и
приёмника не трогает вовсе. До человека этот кусок не доезжает: между «кусок лежит на
полке» и «зритель видит движение» стоит ещё дорога до приёмника и его декодер. Здесь
мерится вся цель целиком, одним числом, и тем же прогоном раскладывается по фазам.

🔴 **Признак живости - двинувшаяся позиция, а не слово.** Приёмник называет себя играющим
раньше картинки, и продуктовый флажок «картинка» ставится по опросу медиастатуса, то есть
с задержкой на шаг опроса. Поэтому щуп не верит ни слову `PLAYING`, ни метке продукта: он
ждёт ДВУХ соседних замеров позиции, которые отличаются.

🔴 **Ход позиции отличается от прыжка ЗАГРУЗКИ физикой, а не порогом.** Загрузка
телепортирует указатель (0 → 437.5 с за 0.34 с), показ его ползёт примерно в реальном
времени (437.539 → 437.558 с за 2.42 с). Отсюда правило :func:`moved`: шаг вперёд
засчитывается движением только если он НЕ больше прошедшего времени. Без этого правила
щуп объявлял бы картинку на посадке закладки, где кадра ещё нет.

⚠️ **Щуп не вытесняет измеряемое.** Ни одного соединения к приёмнику он не открывает:
сендер в системе один - сам показ. Позиция читается СБОКУ, `dumpsys media_session` по adb,
то есть у самой приставки, её же словами о себе. Между прогонами приёмник не трогается.

⚠️ **Потолок средства назван.** Приставка публикует позицию сессии примерно раз в 2 с, и
чаще опроса это число не станет: разрешение замера ограничено приёмником, а не щупом.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from probestamp import run_where, stamp

from torrcast.adapters.filesystem.stopwatch.read import read

#: Медиасессия приёмника Chromecast built-in: её и спрашиваем, остальные сессии приставки
#: (Bluetooth, Spotify) к показу отношения не имеют.
SHELL: Final = "com.google.android.apps.mediashell"
#: Чья это сессия. ⚠️ Между `package=` и `state=` в выводе лежат ещё шесть строк про
#: намерение и флаги, поэтому склеить их в одно правило нельзя: разбор идёт построчно, с
#: памятью о последнем названном хозяине. Первая же попытка склеить дала ноль взглядов.
WHOSE: Final = re.compile(r"^\s*package=(\S+)\s*$")
#: Строка `dumpsys media_session` про состояние сессии. Позиция в ней - в миллисекундах.
PLAY: Final = re.compile(r"state=PlaybackState \{state=(\w+)\(\d+\), position=(-?\d+),")
#: Состояния, при которых сравнивать позицию не с чем: сессия ещё не заряжена показом.
EMPTY: Final = frozenset({"NONE", "IDLE", "ERROR", "STOPPED"})
#: Во сколько раз ход позиции разрешено обгонять часы, прежде чем счесть его прыжком.
SLACK: Final = 1.5
#: Нижний зазор прыжка, с: на шаге опроса меньше него отличать нечего.
FLOOR: Final = 0.5
#: Наименьший ход, который вообще считается движением, с. 🔴 Это КАДР, а не подобранный
#: порог: приёмник иногда уточняет позицию на единицы миллисекунд, не показав ничего, и
#: такое уточнение (21 мс при 25 к/с) объявляло картинку за 2.26 с до метки продукта.
#: Меньше кадра «зритель увидел движение» не значит физически, и опустить порог нечем.
STEP: Final = 0.040
#: Фазы продуктовой ленты, из которых складывается лестница. Берётся ПЕРВОЕ вхождение
#: каждой: заходов упаковки за прогон много, а начало пути одно.
STEPS: Final = (
    "команда",
    "ответы",
    "поиск",
    "индексеры ответили",
    "картина выбрана",
    "отбор релиза",
    "юнит",
    "процесс показа",
    "начало ленты",
    "сетка",
    "раздача",
    "упаковка пошла",
    "первый сегмент",
    "LOAD взят",
)


@dataclass(frozen=True, slots=True)
class Look:
    """Один взгляд на медиасессию приставки: когда, что сказано, где указатель."""

    at: float
    state: str
    pos: float


def look(said: str, now: float) -> Look | None:
    """Выбрать из сырого `dumpsys media_session` состояние сессии приёмника.

    Хозяин сессии назван выше её состояния, а между ними - её флаги, поэтому имя хозяина
    помнится до ближайшей строки состояния. Чужие сессии приставки (Bluetooth, Spotify)
    отсеиваются именно тут: их состояния к показу отношения не имеют.
    """
    whose = ""
    for row in said.splitlines():
        named = WHOSE.match(row)
        if named is not None:
            whose = named.group(1)
            continue
        found = PLAY.search(row)
        if found is not None and whose == SHELL:
            return Look(now, found.group(1), int(found.group(2)) / 1000.0)
    return None


def watch(host: str, stop: threading.Event, seen: list[Look], every: float) -> None:
    """Пассивно читать позицию приставки, пока не велено остановиться.

    Ни одного слова приёмнику не говорится: `dumpsys` спрашивает саму приставку о её
    медиасессии. Часы тут - `time.time()` того же узла, что пишет ленту продукта, поэтому
    метки щупа и метки показа лежат на ОДНОЙ шкале и вычитаются без поправок.
    """
    cmd = ["adb", "-s", host, "shell", "dumpsys media_session"]
    while not stop.is_set():
        now = time.time()
        try:
            said = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            stop.wait(every)
            continue
        found = look(said, now)
        if found is not None:
            seen.append(found)
        stop.wait(every)


def moved(seen: list[Look], since: float = 0.0) -> tuple[Look, Look] | None:
    """Первая пара соседних взглядов, между которыми позиция СДВИНУЛАСЬ показом.

    Возвращается пара «откуда, куда»: числу нужен не только момент, но и то, с чего оно
    снято, иначе «позиция двинулась» не проверить глазами по выводу.

    🔴 ``since`` - пол прогона, и он не формальность. Предыдущий показ приставка гасит не
    мгновенно, и его СВОЁ движение, попав в ленту взглядов, объявило бы картинку раньше
    команды. Считается только то, что увидено после пуска этого прогона.
    """
    prev: Look | None = None
    for spot in seen:
        if spot.at < since:
            continue
        if spot.state in EMPTY:
            prev = None  # сессия пуста: соседа для сравнения нет
            continue
        if prev is not None:
            step, wall = spot.pos - prev.pos, spot.at - prev.at
            if STEP <= step <= wall * SLACK + FLOOR:
                return prev, spot
        prev = spot
    return None


def cold(url: str, keys: bool) -> str:
    """Остудить старт: снести раздачи TorrServer и, если велено, кэш карт опорных кадров.

    Это и есть «заведомо медленное место» поверки: голова раздачи читается из роя заново,
    карта снимается заново, и число обязано вырасти. Приёмник при этом не трогается.

    🔴 Возвращается СДЕЛАННОЕ, а не обещанное. Пока отказ TorrServer глотался молча,
    непроведённое остужение было неотличимо от проведённого: щуп печатал «вход холодный»
    и на прогретом рое, то есть подписывал числу режим, которого не было.
    """
    import requests

    gone, why = 0, ""
    try:
        found = requests.post(f"{url}/torrents", json={"action": "list"}, timeout=20).json()
        for item in found or []:
            requests.post(
                f"{url}/torrents", json={"action": "rem", "hash": item.get("hash")}, timeout=20
            )
            gone += 1
    except Exception as trouble:  # причина уезжает в подпись, а не глотается
        why = f", рой НЕ остужен: {trouble}"
    maps = 0
    if keys:
        for stale in Path("/var/lib/torrcast/keys").glob("*.json"):
            stale.unlink(missing_ok=True)
            maps += 1
    return f"снесено раздач {gone}, карт {maps}{why}; "


def tract(out: Path) -> str:
    """Каким контейнером материал уехал приёмнику - по тому, что лежит на полке.

    Тракт выводится ИЗ ПРОГОНА, а не из константы: один и тот же щуп отдаёт приёмнику
    разные контейнеры, и число, снятое на mpegts, про fmp4 не говорит ничего.
    """
    with contextlib.suppress(OSError):
        if any(out.glob("v*.m4s")):
            return "fmp4"
        if any(out.glob("v*.ts")):
            return "mpegts"
    return "неизвестен"


def ladder(marks: dict[str, float], zero: float, end: float) -> list[tuple[str, float, float]]:
    """Лестница фаз прогона: имя, момент от нуля, цена самой фазы."""
    steps: list[tuple[str, float]] = sorted(
        ((str(n), marks[n]) for n in STEPS if n in marks), key=lambda p: p[1]
    )
    steps.append(("ДВИЖЕНИЕ ПОЗИЦИИ", end))
    return [
        (name, at - zero, at - (steps[i - 1][1] if i else zero))
        for i, (name, at) in enumerate(steps)
    ]


def _args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", default="")
    ap.add_argument("--cold", action="store_true", help="снести рой И кэш карт")
    ap.add_argument("--cold-swarm", action="store_true", help="снести только рой")
    ap.add_argument("--new", action="store_true", help="играть с нуля, а не с закладки")
    ap.add_argument(
        "--config", default=os.environ.get("TORRCAST_CONFIG", "/etc/torrcast/config.json")
    )
    ap.add_argument("--cast", default="/opt/torrcast/venv/bin/cast")
    ap.add_argument("--line", default="/root/framebench.jsonl", help="куда писать ленту меток")
    ap.add_argument("--answers", default="\n\n\n\n\n")
    ap.add_argument("--poll", type=float, default=0.2, help="пауза между взглядами, с")
    ap.add_argument("--timeout", type=float, default=240.0, help="сколько ждать сам cast, с")
    ap.add_argument("--wait", type=float, default=90.0, help="сколько ждать движения после cast, с")
    ap.add_argument("--forget", action="store_true", help="убрать запись состояния: игра ВПЕРВЫЕ")
    ap.add_argument("--state", default="/var/lib/torrcast/state.json")
    ap.add_argument("--trace", default="/root/framebench-looks.jsonl", help="куда класть след")
    ap.add_argument("--settle", type=float, default=6.0, help="дать приёмнику осесть, с")
    ap.add_argument("--card", help="карточка замера; без неё местом станет дата прогона")
    return ap.parse_args()


def main() -> int:
    """Один прогон: остудить по просьбе, пустить показ, дождаться движения, посчитать."""
    args = _args()
    config = json.loads(Path(args.config).read_text("utf-8"))
    host = f"{config['tv']}:5555"
    out = Path(config["hls_dir"])
    line = Path(args.line)
    line.unlink(missing_ok=True)
    chill = ""
    if args.cold or args.cold_swarm:
        chill += cold(config["torrserver_url"], keys=args.cold)

    # Показ идёт ТЕМ ЖЕ конфигом, что у человека: приёмник настоящий, адрес настоящий.
    # Подменяется одна лента меток, и она наружу не смотрит вовсе.
    env = {**os.environ, "TORRCAST_TIMELINE": str(line)}
    # ⚠️ Предыдущий показ гасится ДО начала замера и одинаково перед каждым прогоном:
    # иначе его собственное движение уехало бы в замер нового. Это единственное слово
    # приёмнику за весь прогон, и сказано оно ВНЕ измеряемого промежутка.
    subprocess.run([args.cast, "stop"], env=env, capture_output=True, timeout=60, check=False)
    time.sleep(args.settle)
    if args.forget:
        # 🔴 Запись уносится ПОСЛЕ остановки прошлого показа, а не до неё. `cast stop`
        # сохраняет закладку уходящего показа, и унесённое до него состояние он писал
        # заново: щуп подписывал числу «играю впервые», а показ продолжал с середины.
        # Уносится В СТОРОНУ, а не стирается: закладки стенда чужие.
        kept = Path(args.state)
        if kept.exists():
            kept.rename(kept.with_suffix(f".json.before-{int(time.time())}"))
            chill = f"{chill}запись состояния унесена ПОСЛЕ остановки; "
    if chill:
        print(f"остужение: {chill.strip('; ')}")

    seen: list[Look] = []
    stop = threading.Event()
    eye = threading.Thread(target=watch, args=(host, stop, seen, args.poll), daemon=True)
    eye.start()
    floor = time.time()
    said = subprocess.run(
        [args.cast, *( ["--new"] if args.new else [] ), args.query],
        input=args.answers, env=env, capture_output=True, text=True,
        timeout=args.timeout, check=False,
    )  # fmt: skip
    # 🔴 `cast` уходит по слову приёмника, а движения к этому моменту может ещё не быть:
    # ровно этот хвост и есть то, чего не мерил никто. Ждём его ПОСЛЕ ухода команды.
    until = time.monotonic() + args.wait
    while time.monotonic() < until and moved(seen, floor) is None:
        time.sleep(args.poll)
    stop.set()
    eye.join(timeout=15.0)

    # 🔴 След прогона ложится на диск ЦЕЛИКОМ: без него число нечем перепроверить, а
    # правило движения нечем судить иначе как новым прогоном на изменившемся стенде.
    Path(args.trace).write_text(
        "\n".join(json.dumps(asdict(spot), ensure_ascii=False) for spot in seen), "utf-8"
    )
    print(said.stdout.rstrip())
    marks: dict[str, float] = {}
    for row in read(line):
        marks.setdefault(str(row["name"]), float(row["at"]))
    pair = moved(seen, floor)
    if "команда" not in marks or pair is None:
        print(
            f"🔴 замера нет: меток {len(marks)}, взглядов {len(seen)}, "
            f"движение {'не поймано' if pair is None else 'есть'}",
            file=sys.stderr,
        )
        return 1
    was, now = pair
    zero = marks["команда"]
    full = now.at - zero
    print(f"\n--- фазы прогона (ноль = «команда»), взглядов на приставку {len(seen)} ---")
    rungs = ladder(marks, zero, now.at)
    for name, since, cost in rungs:
        print(f"{since:7.2f} с  +{cost:6.2f} с  {name}")
    total = sum(cost for _, _, cost in rungs)
    print(f"\nПОЛНОЕ (команда → движение позиции): {full:.2f} с")
    print(f"сумма фаз {total:.2f} с · расхождение с полным {full - total:+.2f} с")
    # ⚠️ Лестница телескопична и часы у неё одни, поэтому расхождение выше равно нулю
    # ПО ПОСТРОЕНИЮ и доказательством покрытия пути не является. Доказывает его хвост
    # ниже: это единственная фаза, которую продуктовые метки не называют вовсе.
    print(f"движение: {was.pos:.3f} → {now.pos:.3f} с за {now.at - was.at:.2f} с, {now.state}")
    tail = now.at - max(marks[n] for n in STEPS if n in marks)
    print(f"хвост после последней метки продукта: {tail:.2f} с")
    if "картинка" in marks:
        print(f"метка продукта «картинка» против движения: {marks['картинка'] - now.at:+.2f} с")
    entry = "холодный" if args.cold else "холодный рой" if args.cold_swarm else "прогретый"
    print(
        stamp(
            "framebench",
            tract(out),
            run_where(args.card),
            [
                f"приёмник {config['tv']}",
                f"опрос {args.poll:.2f} с",
                f"вход {entry}" + (f" ({chill.strip('; ')})" if chill else ""),
            ],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
