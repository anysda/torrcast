#!/usr/bin/env python3
"""Меряет, сдаётся ли отвод захода на границах сетки и как широки провалы между посадками.

Правило отвода щуп не повторяет, а зовёт: :func:`settle_start` принимает измеритель
доводом, и сюда он получает настоящий пробный прогон ffmpeg. Поэтому щуп меряет ровно то
правило, которое работает у зрителя, а не свою копию его.

Прогон отвергается не по коду возврата: ffmpeg умеет выйти нулём, напечатав ошибку
демультиплексирования или мультиплексирования. Признаком удачи считается прочитанный
первый пакет, и только он.

    python3 scripts/seekgaps.py URL --duration 7200
    python3 scripts/seekgaps.py URL --duration 7200 --step 10 --deeper 2

На stdout пишется JSONL: сначала одна строка на границу, затем итоговая строка. Щуп ничего
не знает о каталоге, раздаче и стенде; URL и длительность задаёт измеряющий.

Место посадки переводится в ленту фильма - ту, в которой стоят границы сетки. У .m2ts
видео начинается с тысяч секунд, и без перевода каждая посадка оказалась бы «позже
границы» на весь сдвиг разом.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# Щуп зовёт продукт и обязан звать СВОЙ: editable-установка венва смотрит на соседний
# клон, и без этой строки замер снимался бы кодом, который правят в чужой работе.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.adapters.stream_pack.settle_start import SEEK_BACK_TRIES, settle_start
from torrcast.domain.hls_settings import HLS_SEGMENT_SECONDS, SPLIT_SLACK

#: Заход встал не позже границы, отвод не понадобился вовсе.
AT_ONCE = "сразу"
#: Заход уехал вперёд, но отвод нашёл место не позже границы.
SETTLED = "отведён"
#: Отвод исчерпал свои шаги, и кусок границы начнётся позже своего имени.
GAVE_UP = "сдался"
#: Место посадки не измерено: прогон не дал первого пакета.
UNMEASURED = "не измерено"


class UnreachableError(Exception):
    """Пробный прогон не дал первого пакета: мерить на этой границе нечего."""


@dataclass(frozen=True, slots=True)
class Outcome:
    """Чем кончилось правило отвода на одной границе."""

    at: float
    stood: float | None
    settled: float | None
    asked: int
    kind: str
    rescued: int | None = None
    error: str = ""


def boundaries(duration: float, step: float) -> list[float]:
    """Все ненулевые начала сегментов той же равномерной сетки, что у упаковки."""
    count = max(1, math.ceil((max(duration, 0.0) - step / 2) / step))
    return [step * slot for slot in range(1, count)]


def _run_error(stderr: str) -> str:
    """Строка ffmpeg, отменяющая удачу прогона; пусто - таких строк нет.

    Ошибка мультиплексирования тут наравне с ошибкой демультиплексирования: mpegts
    отказывается принимать поток без меток (``first pts and dts value must be set``),
    печатает это и выходит НУЛЁМ, оставив пустой файл.
    """
    marks = (
        "error during demuxing",
        "input/output error",
        "error muxing a packet",
        "error submitting a packet",
        "must be set",
    )
    for line in stderr.splitlines():
        folded = line.casefold()
        if any(mark in folded for mark in marks):
            return line.strip()
    return ""


def land(url: str, at: float, timeout: float) -> tuple[float | None, str]:
    """Один боевой пробный прогон; ошибка названа отдельно от места посадки.

    Команда та же, которой место посадки меряет сам показ: ``-copyts`` держит метки как
    они лежат в файле, а ``-muxdelay 0 -muxpreload 0`` не дают мультиплексору добавить к
    ним свои 1.4 с - без них «первый кадр» оказался бы не там, где он есть.
    """
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
        broke = _run_error(done.stderr)
        if done.returncode != 0 or broke:
            tail = broke or next(
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


def film_begins(url: str, timeout: float) -> float:
    """С какой метки начинается ВИДЕО файла: тем же правилом, каким её узнаёт показ.

    Спрашивается ровно видео, а не контейнер целиком: ``start_time`` формата - минимум по
    всем потокам, а звук начинается на набивку кодировщика раньше видео. У семейства mp4
    сдвига нет по построению, и там ответ назначается нулём, а не считается.

    ⚠️ Строки берутся первая и последняя из непустых, а не по номеру: mpegts печатает на
    тот же запрос ЧЕТЫРЕ строки (метка, пустая, метка ещё раз, имя контейнера), тогда как
    matroska и avi - две. По номеру строки имя контейнера у mpegts попадает на пустую.
    """
    try:
        answer = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=start_time:format=format_name", "-of", "csv=p=0", url],
            capture_output=True, text=True, timeout=timeout, check=True,
        )  # fmt: skip
        lines = [line.strip() for line in answer.stdout.splitlines() if line.strip()]
        value = float(lines[0].split(",")[0])
        container = lines[-1].strip('"').split(",")[0]
    except (OSError, subprocess.SubprocessError, IndexError, ValueError):
        return 0.0
    if not math.isfinite(value) or container == "mov":
        return 0.0
    return value


@dataclass
class Pilot:
    """Измеритель, который правило отвода зовёт доводом; помнит всё, что видел.

    Место посадки для одного и того же ``-ss`` не меняется, поэтому повторный вопрос
    отвечается из памяти. Считаются обе цены: сколько раз правило спросило и сколько
    прогонов ffmpeg за этим поднялось.

    ``begins`` - с какой метки начинается ВИДЕО файла. Ответ переводится в ленту фильма
    ровно так же, как это делает показ: ``-ss`` отсчитывается от начала видео, а
    ``-copyts`` печатает метку вместе со сдвигом всего контейнера, и у .m2ts эти два
    числа расходятся на тысячи секунд (замер: видео начинается с 4199.167). Не вычесть
    сдвиг - и каждая посадка окажется «позже границы» на весь сдвиг разом, то есть
    правило отвода мерилось бы на выдуманном провале.
    """

    url: str
    timeout: float
    begins: float = 0.0
    seen: dict[float, float] = field(default_factory=dict)
    asks: int = 0
    runs: int = 0

    def __call__(self, url: str, at: float, timeout: float, keys: object = None) -> float:
        self.asks += 1
        key = round(at, 3)
        remembered = self.seen.get(key)
        if remembered is not None:
            return remembered
        self.runs += 1
        stood, error = land(url, at, timeout)
        if stood is None:
            raise UnreachableError(error)
        self.seen[key] = stood - self.begins
        return self.seen[key]


def deeper(pilot: Pilot, at: float, stood: float, extra: int) -> int | None:
    """Каким по счёту шагом отвод накрыл бы границу, будь потолок выше; ``None`` - никаким.

    Продолжает то же удвоение с того места, где правило остановилось: цена поднятого
    потолка считается прогонами, а польза - спасёнными границами.
    """
    back = max(stood - at, HLS_SEGMENT_SECONDS) * float(2**SEEK_BACK_TRIES)
    for step in range(1, extra + 1):
        seek = max(0.0, at - back)
        found = pilot(pilot.url, seek, pilot.timeout)
        if found <= at + SPLIT_SLACK:
            return SEEK_BACK_TRIES + step
        if seek <= 0.0:
            break
        back *= 2.0
    return None


def outcome(pilot: Pilot, at: float, extra: int) -> Outcome:
    """Прогнать правило отвода на одной границе и назвать, чем оно кончилось."""
    before = pilot.asks
    try:
        _, settled = settle_start(pilot.url, at, pilot.timeout, None, start=pilot)
    except UnreachableError as exc:
        return Outcome(at, None, None, pilot.asks - before, UNMEASURED, error=str(exc))
    asked = pilot.asks - before
    stood = pilot.seen[round(at, 3)]
    if asked == 1:
        return Outcome(at, stood, settled, asked, AT_ONCE)
    if settled <= at + SPLIT_SLACK:
        return Outcome(at, stood, settled, asked, SETTLED)
    rescued = None
    if extra > 0:
        try:
            rescued = deeper(pilot, at, stood, extra)
        except UnreachableError:
            rescued = None
    return Outcome(at, stood, settled, pilot.asks - before, GAVE_UP, rescued=rescued)


def widest(rows: list[Outcome]) -> tuple[float | None, float | None, float]:
    """Самый широкий провал между разными местами, куда демуксер согласился сесть."""
    reached = sorted({row.stood for row in rows if row.stood is not None})
    gaps = [(left, right, right - left) for left, right in itertools.pairwise(reached)]
    return max(gaps, key=lambda gap: gap[2], default=(None, None, 0.0))


def summary(rows: list[Outcome], pilot: Pilot, duration: float, step: float) -> dict[str, object]:
    """Итог по одному релизу: чем кончилось правило и как широки провалы."""
    kinds = {name: sum(row.kind == name for row in rows) for name in (AT_ONCE, SETTLED, GAVE_UP)}
    lost = [row for row in rows if row.kind == UNMEASURED]
    given = [row for row in rows if row.kind == GAVE_UP]
    left, right, gap = widest(rows)
    return {
        "итог": True,
        "длительность": duration,
        "шаг": step,
        "границ": len(rows),
        "измерено": len(rows) - len(lost),
        UNMEASURED: len(lost),
        "сразу": kinds[AT_ONCE],
        "отведён": kinds[SETTLED],
        "сдался": kinds[GAVE_UP],
        "границы сдачи": [row.at for row in given],
        "спасли бы шагом": [row.rescued for row in given],
        "различных посадок": len({row.stood for row in rows if row.stood is not None}),
        "самый широкий провал": round(gap, 6),
        "между": [left, right],
        "шире 80 с": gap > 80.0,
        "начало видео": round(pilot.begins, 3),
        "спрошено правилом": pilot.asks,
        "прогонов ffmpeg": pilot.runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Замер отвода захода на границах сетки")
    parser.add_argument("url")
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--step", type=float, default=HLS_SEGMENT_SECONDS)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--deeper",
        type=int,
        default=2,
        help="сколько шагов сверх потолка пробовать там, где отвод сдался",
    )
    args = parser.parse_args()
    if args.duration <= 0 or args.step <= 0 or args.timeout <= 0 or args.deeper < 0:
        parser.error("длительность, шаг и таймаут положительны, число лишних шагов неотрицательно")
    pilot = Pilot(args.url, args.timeout, film_begins(args.url, args.timeout))
    rows = []
    for at in boundaries(args.duration, args.step):
        row = outcome(pilot, at, args.deeper)
        rows.append(row)
        print(
            json.dumps(
                {
                    "граница": row.at,
                    "посадка": row.stood,
                    "осело": row.settled,
                    "спрошено": row.asked,
                    "исход": row.kind,
                    "спас шаг": row.rescued,
                    "ошибка": row.error,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    report = summary(rows, pilot, args.duration, args.step)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 2 if report[UNMEASURED] else 0


if __name__ == "__main__":
    raise SystemExit(main())
